"""LDAP authentication, role assignment, and server-side sessions.

Two rules shape this module.

**The directory authenticates; it does not authorise.** LDAP answers "who are you" and "which of
the two ContextGuard groups are you in". Which *repositories* you may see is a GitHub question, so
it is not answered here.

**Passwords are never stored, compared, or logged.** A login is verified by re-binding to the
directory *as the user* with the password they supplied. Reading a hash and comparing it would only
prove the password is readable; binding proves it is theirs.

Every pure part - group matching, role mapping, expiry arithmetic - is kept out of the I/O path so
it can be tested without a directory server. See tests/test_auth.py.
"""
import logging
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import settings
from app.crypto import CryptoKeyMissing, TokenDecryptionError, decrypt_token, encrypt_token
from app.db import connect

logger = logging.getLogger("app-aware-reviewer")

ADMIN = "admin"
USER = "user"


@dataclass(frozen=True)
class LdapUser:
    username: str
    dn: str
    role: str
    display_name: str = ""


# --- pure: group and role mapping ----------------------------------------------------------

def _normalise_dn(dn: str) -> str:
    """Lowercase and drop whitespace around separators, so formatting differences do not matter."""
    return ",".join(part.strip() for part in (dn or "").split(",")).lower()


def group_matches(memberof_value: str, configured: str) -> bool:
    """Does one `memberOf` value refer to the configured group?

    A bare CN ("CONTEXTGUARD-ADMIN") is matched against the CN component of the DN, so moving the
    group to a different OU does not silently revoke everyone. A configured value containing "=" is
    treated as a full DN and compared exactly, for directories where a CN alone is ambiguous.
    """
    value = (memberof_value or "").strip().lower()
    target = (configured or "").strip().lower()
    if not value or not target:
        return False
    if "=" in target:
        return _normalise_dn(value) == _normalise_dn(target)
    for part in value.split(","):
        key, _, val = part.partition("=")
        if key.strip() == "cn" and val.strip() == target:
            return True
    return False


def role_from_memberof(memberof: list[str] | None, admin_group: str, user_group: str) -> str | None:
    """`admin`, `user`, or None meaning "refuse this login".

    Admin is checked first, so somebody in both groups is an admin rather than depending on
    attribute ordering.
    """
    values = [value for value in (memberof or []) if value]
    if any(group_matches(value, admin_group) for value in values):
        return ADMIN
    if any(group_matches(value, user_group) for value in values):
        return USER
    return None


# --- pure: sessions ------------------------------------------------------------------------

def new_session_id() -> str:
    """256 bits of URL-safe randomness.

    Unguessable, which is why the cookie carries it raw: there is nothing to sign, and a forged
    cookie cannot collide with a real one. The session itself lives server-side so it can be
    revoked, which a self-contained signed token could not be.
    """
    return secrets.token_urlsafe(32)


def expiry_for(now: datetime, ttl_hours: int) -> datetime:
    return now + timedelta(hours=max(1, ttl_hours))


def is_expired(expires_at: datetime, now: datetime) -> bool:
    return now >= expires_at


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# --- sessions, persisted -------------------------------------------------------------------

SESSION_COLS = ("id, username, ldap_dn, display_name, role, github_login, github_repos,"
                " github_repos_at, expires_at, last_seen_at")


def _row_to_session(row) -> dict:
    return {"id": row[0], "username": row[1], "ldap_dn": row[2], "display_name": row[3],
            "role": row[4], "github_login": row[5], "github_repos": list(row[6] or []),
            "github_repos_at": row[7], "expires_at": row[8], "last_seen_at": row[9]}


def needs_touch(session: dict, now: datetime, interval_seconds: int = 60) -> bool:
    """Whether `last_seen_at` is stale enough to be worth writing.

    Every asset request passes through the middleware, so an unconditional UPDATE would be a
    database write per request. Once a minute is ample to keep an active session observably alive.
    """
    last_seen = session.get("last_seen_at")
    if last_seen is None:
        return True
    return (now - last_seen).total_seconds() >= interval_seconds


def create_session(user: LdapUser) -> str:
    session_id = new_session_id()
    with connect() as conn:
        conn.execute("""INSERT INTO sessions(id, username, ldap_dn, display_name, role, expires_at)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            (session_id, user.username, user.dn, user.display_name, user.role,
             expiry_for(now_utc(), settings.session_ttl_hours)))
        conn.commit()
    return session_id


def load_session(session_id: str | None) -> dict | None:
    """The session, or None if it is missing or has expired. Expired rows are removed on sight."""
    if not session_id:
        return None
    with connect() as conn:
        row = conn.execute(f"SELECT {SESSION_COLS} FROM sessions WHERE id=%s", (session_id,)).fetchone()
    if not row:
        return None
    session = _row_to_session(row)
    if is_expired(session["expires_at"], now_utc()):
        delete_session(session_id)
        return None
    return session


def touch_session(session_id: str) -> None:
    with connect() as conn:
        conn.execute("UPDATE sessions SET last_seen_at=now() WHERE id=%s", (session_id,))
        conn.commit()


def delete_session(session_id: str) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM sessions WHERE id=%s", (session_id,))
        conn.commit()


def purge_expired_sessions() -> int:
    with connect() as conn:
        removed = conn.execute("DELETE FROM sessions WHERE expires_at < now()").rowcount
        conn.commit()
    return removed


def store_github_identity(session_id: str, login: str, repos: list[str], token: str) -> None:
    """Persist the OAuth result.

    The token is encrypted with the same Fernet key as owner credentials - same helper, same key,
    so there is no second scheme to rotate. If that key is unset we refuse rather than fall back to
    plaintext: a user's GitHub token is not less sensitive than an owner token.
    """
    ciphertext = encrypt_token(token, settings.github_credential_key)
    with connect() as conn:
        conn.execute("""UPDATE sessions SET github_login=%s, github_repos=%s,
            github_repos_at=now(), github_token_ciphertext=%s WHERE id=%s""",
            (login, repos, ciphertext, session_id))
        conn.commit()


def session_github_token(session_id: str) -> str | None:
    """The session's GitHub token, decrypted. None when not connected, or on a key mismatch."""
    with connect() as conn:
        row = conn.execute("SELECT github_token_ciphertext FROM sessions WHERE id=%s",
                           (session_id,)).fetchone()
    if not row or not row[0]:
        return None
    try:
        return decrypt_token(row[0], settings.github_credential_key)
    except (TokenDecryptionError, CryptoKeyMissing):
        logger.error("Stored GitHub token for a session could not be decrypted")
        return None


def forget_github_identity(session_id: str) -> None:
    with connect() as conn:
        conn.execute("""UPDATE sessions SET github_login=NULL, github_repos=NULL,
            github_repos_at=NULL, github_token_ciphertext=NULL WHERE id=%s""", (session_id,))
        conn.commit()


# --- LDAP ----------------------------------------------------------------------------------

def _ldap_server():
    """ldap3 wants the host and the scheme separately; accept either form in config."""
    from ldap3 import Server
    raw = (settings.ldap_server or "").strip()
    use_ssl = raw.lower().startswith("ldaps://")
    host = raw.split("://", 1)[-1]
    return Server(host, use_ssl=use_ssl, connect_timeout=settings.ldap_timeout_seconds)


def _values(entry, attribute: str) -> list[str]:
    if attribute not in entry:
        return []
    raw = entry[attribute].values
    if isinstance(raw, (list, tuple)):
        return [str(value) for value in raw]
    return [str(raw)]


def authenticate(username: str, password: str) -> tuple[LdapUser | None, str]:
    """(user, reason). `reason` is empty on success, and display-ready otherwise.

    Misses deliberately share one message - "no such user" and "wrong password" are not
    distinguished, so the form cannot be used to enumerate directory accounts.
    """
    from ldap3 import Connection, SUBTREE
    from ldap3.core.exceptions import LDAPException
    from ldap3.utils.conv import escape_filter_chars

    if not settings.ldap_configured:
        return None, "Directory sign-in is not configured on this server."

    username = (username or "").strip()
    if not username or not password:
        return None, "Enter both a username and a password."

    attribute = settings.ldap_user_attribute
    # The username reaches an LDAP filter, so it is escaped: an unescaped value could otherwise
    # close the clause and change what is matched.
    search_filter = f"(&(objectClass=person)({attribute}={escape_filter_chars(username)}))"
    denied = "Incorrect username or password."

    try:
        server = _ldap_server()
        with Connection(server, user=settings.ldap_bind_dn, password=settings.ldap_bind_password,
                        receive_timeout=settings.ldap_timeout_seconds, auto_bind=True) as conn:
            conn.search(settings.ldap_base_dn, search_filter, search_scope=SUBTREE,
                        attributes=[attribute, "displayName", "memberOf", "cn"])
            if not conn.entries:
                return None, denied
            entry = conn.entries[0]
            dn = entry.entry_dn
            memberof = _values(entry, "memberOf")
            display_name = (_values(entry, "displayName") or [username])[0]
    except LDAPException as exc:
        logger.exception("LDAP search failed for %s", username)
        return None, f"Could not reach the directory ({type(exc).__name__})."

    role = role_from_memberof(memberof, settings.ldap_admin_group, settings.ldap_user_group)
    if role is None:
        # Membership is checked before the password, so an unentitled account is refused without
        # its password ever being sent to the directory.
        return None, (f"Your account is not a member of {settings.ldap_admin_group} or "
                      f"{settings.ldap_user_group}.")

    try:
        with Connection(server, user=dn, password=password,
                        receive_timeout=settings.ldap_timeout_seconds, auto_bind=True):
            pass
    except LDAPException:
        return None, denied

    return LdapUser(username=username, dn=dn, role=role, display_name=display_name), ""
