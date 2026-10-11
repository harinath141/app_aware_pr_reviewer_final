"""Per-owner GitHub credentials, stored encrypted and resolved per webhook.

The app has no authentication by design, so: every mutation is audited, no endpoint ever returns
token material, and `serialize_credential` cannot emit a secret because its SELECT never reads one.
"""
import logging

import httpx

from app.config import settings
from app.crypto import (TokenDecryptionError, decrypt_token, encrypt_token, is_valid_key,
                        key_fingerprint, mask_token)
from app.db import connect
from app.github_client import GitHubClient

logger = logging.getLogger("app-aware-reviewer")

# Verification outcomes. Everything except BAD_CREDENTIALS and ERROR is stored (with a warning).
OK = "ok"
NO_REPO_ACCESS = "no_repo_access"
OWNER_INVISIBLE = "owner_invisible"
INSUFFICIENT_SCOPE = "insufficient_scope"
BAD_CREDENTIALS = "bad_credentials"
RATE_LIMITED = "rate_limited"
ERROR = "error"

REJECTED = {BAD_CREDENTIALS, ERROR}

# Never includes token_ciphertext: serialize_credential therefore cannot leak a secret.
CRED_COLS = ("owner, owner_login, token_hint, verified_login, scopes, repo_access_count, "
             "owner_is_org, last_verified_at, last_verification_status, last_verification_detail, "
             "created_at, updated_at")

def normalize_owner(login: str) -> str:
    """GitHub logins are case-insensitive but case-preserving; key on the lowercase form."""
    return (login or "").strip().lower()

def choose_token(stored: str | None, global_token: str | None) -> tuple[str | None, str]:
    """Precedence rule, kept pure so it can be tested without a database."""
    if stored:
        return stored, "owner"
    if global_token:
        return global_token, "global"
    return None, "none"

def key_status() -> str:
    """'ok' | 'missing' | 'invalid' - drives the write refusal and the dashboard banner."""
    key = settings.github_credential_key
    if not key:
        return "missing"
    return "ok" if is_valid_key(key) else "invalid"

def _iso(value):
    return value.isoformat() if value else None

def serialize_credential(row) -> dict:
    """The only shape a credential takes on the way out of the app."""
    return {"owner": row[0], "owner_login": row[1], "token_hint": row[2],
            "verified_login": row[3], "scopes": row[4], "repo_access_count": row[5],
            "owner_is_org": row[6], "last_verified_at": _iso(row[7]),
            "last_verification_status": row[8], "last_verification_detail": row[9],
            "created_at": _iso(row[10]), "updated_at": _iso(row[11])}

def audit(owner: str, action: str, *, addr: str | None = None, chain: str | None = None,
          ua: str | None = None, detail: str | None = None) -> None:
    """Record a credential mutation. Never raises - auditing must not break the operation."""
    try:
        with connect() as conn:
            conn.execute("""INSERT INTO credential_audit(owner, action, actor_addr,
                actor_forwarded_chain, actor_ua, detail) VALUES (%s,%s,%s,%s,%s,%s)""",
                (normalize_owner(owner), action, addr, chain, ua, detail))
    except Exception:
        logger.exception("could not write credential audit owner=%s action=%s", owner, action)

# --- resolution ---------------------------------------------------------------------------

def resolve_token(owner: str) -> tuple[str | None, str]:
    """Return (token, source) for an owner, falling back to the global .env token.

    One indexed primary-key SELECT per webhook, so an updated credential takes effect on the
    very next delivery with no cache to invalidate.
    """
    key = settings.github_credential_key
    with connect() as conn:
        row = conn.execute("SELECT token_ciphertext FROM owner_credentials WHERE owner=%s",
                           (normalize_owner(owner),)).fetchone()
    if row is None:
        return choose_token(None, settings.github_token)
    if not key:
        logger.error("credential for owner=%s exists but GITHUB_CREDENTIAL_KEY is unset; "
                     "falling back to the global token", owner)
        return choose_token(None, settings.github_token)
    try:
        return choose_token(decrypt_token(row[0], key), settings.github_token)
    except TokenDecryptionError:
        logger.error("credential for owner=%s could not be decrypted (key changed?); "
                     "falling back to the global token", owner)
        audit(owner, "decrypt_failed", detail="encryption key mismatch")
        return choose_token(None, settings.github_token)

class NoCredentialError(RuntimeError):
    """Neither a stored credential nor a global fallback exists for this owner."""

class _FallbackClient:
    """GitHubClient proxy that retries once with the global token if the owner's is rejected.

    Implemented as a proxy so the webhook handler stays untouched: any call that comes back
    401/403 re-runs against the global token and the client stays switched for the rest of the
    request. Retrying is safe because a 401/403 means GitHub rejected the call outright, so
    nothing was created by the first attempt.
    """

    def __init__(self, owner: str, token: str, source: str):
        self._owner = owner
        self._token = token
        self._source = source
        self._client = GitHubClient(token)
        self._switched = False

    @property
    def source(self) -> str:
        """'owner' or 'global' - changes to 'global' if the fallback fired."""
        return self._source

    def __getattr__(self, name):
        attr = getattr(self._client, name)
        if not callable(attr):
            return attr

        async def call(*args, **kwargs):
            try:
                return await attr(*args, **kwargs)
            except httpx.HTTPStatusError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if (status in (401, 403) and self._source == "owner" and not self._switched
                        and settings.github_token and settings.github_token != self._token):
                    self._switched = True
                    mark_credential_failed(self._owner, f"GitHub returned {status} during a review")
                    logger.warning("credential for owner=%s rejected (%s); retrying with the "
                                   "global token", self._owner, status)
                    self._client = GitHubClient(settings.github_token)
                    self._source = "global"
                    return await getattr(self._client, name)(*args, **kwargs)
                raise
        return call

def credential_client(owner: str) -> _FallbackClient:
    """Client for an owner, with automatic fallback to the global token."""
    token, source = resolve_token(owner)
    if not token:
        raise NoCredentialError(f"no GitHub credential configured for {owner}")
    return _FallbackClient(owner, token, source)

def stored_token(owner: str) -> str | None:
    """Decrypted token for an owner, or None. Used by the re-verify route."""
    key = settings.github_credential_key
    with connect() as conn:
        row = conn.execute("SELECT token_ciphertext FROM owner_credentials WHERE owner=%s",
                           (normalize_owner(owner),)).fetchone()
    if not row or not key:
        return None
    return decrypt_token(row[0], key)

# --- storage ------------------------------------------------------------------------------

def list_credentials() -> list[dict]:
    with connect() as conn:
        rows = conn.execute(f"SELECT {CRED_COLS} FROM owner_credentials"
                            " ORDER BY owner").fetchall()
    return [serialize_credential(r) for r in rows]

def get_credential(owner: str) -> dict | None:
    with connect() as conn:
        row = conn.execute(f"SELECT {CRED_COLS} FROM owner_credentials WHERE owner=%s",
                           (normalize_owner(owner),)).fetchone()
    return serialize_credential(row) if row else None

def save_credential(owner: str, owner_login: str, token: str, verification: dict) -> dict:
    key = settings.github_credential_key
    with connect() as conn:
        conn.execute("""INSERT INTO owner_credentials(owner, owner_login, token_ciphertext,
            token_hint, key_fingerprint, verified_login, scopes, repo_access_count, owner_is_org,
            last_verified_at, last_verification_status, last_verification_detail)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s)
            ON CONFLICT(owner) DO UPDATE SET owner_login=EXCLUDED.owner_login,
              token_ciphertext=EXCLUDED.token_ciphertext, token_hint=EXCLUDED.token_hint,
              key_fingerprint=EXCLUDED.key_fingerprint, verified_login=EXCLUDED.verified_login,
              scopes=EXCLUDED.scopes, repo_access_count=EXCLUDED.repo_access_count,
              owner_is_org=EXCLUDED.owner_is_org, last_verified_at=now(),
              last_verification_status=EXCLUDED.last_verification_status,
              last_verification_detail=EXCLUDED.last_verification_detail, updated_at=now()""",
            (normalize_owner(owner), owner_login or owner, encrypt_token(token, key),
             mask_token(token), key_fingerprint(key), verification.get("verified_login"),
             verification.get("scopes"), verification.get("repo_access_count"),
             verification.get("owner_is_org"), verification.get("status"),
             verification.get("detail")))
    return get_credential(owner)

def record_verification(owner: str, verification: dict) -> None:
    with connect() as conn:
        conn.execute("""UPDATE owner_credentials SET last_verified_at=now(),
            last_verification_status=%s, last_verification_detail=%s, updated_at=now()
            WHERE owner=%s""", (verification.get("status"), verification.get("detail"),
                                normalize_owner(owner)))

def mark_credential_failed(owner: str, detail: str) -> None:
    """Record that GitHub rejected this credential at review time, so the UI can show it."""
    try:
        with connect() as conn:
            conn.execute("""UPDATE owner_credentials SET last_verification_status=%s,
                last_verification_detail=%s, updated_at=now() WHERE owner=%s""",
                (BAD_CREDENTIALS, detail[:500], normalize_owner(owner)))
    except Exception:
        logger.exception("could not mark credential failed owner=%s", owner)

def delete_credential(owner: str) -> bool:
    with connect() as conn:
        row = conn.execute("DELETE FROM owner_credentials WHERE owner=%s RETURNING owner",
                           (normalize_owner(owner),)).fetchone()
    return row is not None

# --- verification -------------------------------------------------------------------------

def classify_verification(*, org_status: int | None, user_status: int | None,
                          repo_status: int | None, repo_count: int | None,
                          is_org: bool, rate_limited: bool = False) -> str:
    """Pure decision over the probe results, so the truth table is unit-testable.

    GitHub answers 404 rather than 403 for private things a token cannot see, so a bare 404 is
    ambiguous and has to be combined with the org/user lookups before it means anything.
    """
    if org_status == 403 or repo_status == 403:
        return RATE_LIMITED if rate_limited else INSUFFICIENT_SCOPE
    if not is_org and user_status == 404:
        return OWNER_INVISIBLE
    if repo_count == 0:
        # Legitimate: a fine-grained PAT can be scoped to zero repos at save time.
        return NO_REPO_ACCESS
    return OK

def _header(headers: dict, name: str) -> str:
    for k, v in headers.items():
        if k.lower() == name.lower():
            return v or ""
    return ""

def _rate_limited(headers: dict) -> bool:
    return _header(headers, "x-ratelimit-remaining") == "0"

async def verify_owner_token(owner: str, token: str) -> dict:
    """Prove a token is live and can see the owner. Returns a verdict, never raises.

    Honest limit: fine-grained PATs expose no scopes header and no permission bits over REST, so
    this proves authenticity and visibility only - never that the token has Pull requests:write.
    """
    gh = GitHubClient(token)
    try:
        status, user, headers = await gh.probe_json("/user")
        if status in (401, 403):
            return {"status": BAD_CREDENTIALS, "http_status": 400,
                    "detail": f"GitHub rejected the token (GET /user returned {status})."}
        if status != 200 or not isinstance(user, dict):
            return {"status": ERROR, "http_status": 503,
                    "detail": f"Unexpected response from GitHub (GET /user returned {status})."}

        scopes = _header(headers, "x-oauth-scopes").strip() or None
        verified_login = user.get("login")

        org_status, _, _ = await gh.probe_json(f"/orgs/{owner}")
        is_org = org_status == 200
        user_status = None
        if not is_org:
            user_status, _, _ = await gh.probe_json(f"/users/{owner}")

        repo_status, repo_count, rate_limited = None, None, False
        if is_org:
            repo_status, repos, rh = await gh.probe_json(
                f"/orgs/{owner}/repos?per_page=100&type=all")
            rate_limited = _rate_limited(rh)
            if repo_status == 200 and isinstance(repos, list):
                repo_count = len(repos)
        elif user_status == 200:
            repo_status, repos, rh = await gh.probe_json(
                "/user/repos?per_page=100&affiliation=owner,organization_member")
            rate_limited = _rate_limited(rh)
            if repo_status == 200 and isinstance(repos, list):
                prefix = normalize_owner(owner) + "/"
                repo_count = sum(1 for r in repos
                                 if (r.get("full_name") or "").lower().startswith(prefix))

        verdict = classify_verification(org_status=org_status, user_status=user_status,
                                        repo_status=repo_status, repo_count=repo_count,
                                        is_org=is_org, rate_limited=rate_limited)
        return {"status": verdict, "verified_login": verified_login, "scopes": scopes,
                "repo_access_count": repo_count, "owner_is_org": is_org,
                "http_status": 200 if verdict == OK else 200, "detail": _detail(verdict, owner)}
    except Exception as exc:
        logger.exception("credential verification errored owner=%s", owner)
        return {"status": ERROR, "http_status": 503,
                "detail": f"Could not reach GitHub ({type(exc).__name__})."}

def _detail(verdict: str, owner: str) -> str | None:
    return {
        NO_REPO_ACCESS: f"Saved, but this token can see 0 repositories under {owner}.",
        OWNER_INVISIBLE: f"Saved, but {owner} was not visible to this token.",
        INSUFFICIENT_SCOPE: f"Saved, but the token may lack access to {owner}.",
        RATE_LIMITED: "Saved, but GitHub rate-limited the access check - re-verify later.",
    }.get(verdict)
