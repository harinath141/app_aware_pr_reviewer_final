"""Session enforcement, CSRF, and the cookie plumbing for the browser-facing app.

**This module is an allowlist, not a blocklist.** Only the paths named in PUBLIC_EXACT and
PUBLIC_PREFIXES are reachable without a session; everything else - including routes added later by
somebody who has never read this file - is protected by default. Reversing that is the failure mode
that matters here: a single unprotected route exposes every repository's findings *and* the
credential endpoints, and the exposure is silent.
"""
import hmac
import logging
import secrets

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from app import auth
from app.config import settings

logger = logging.getLogger("app-aware-reviewer")

SESSION_COOKIE = "cg_session"
CSRF_COOKIE = "cg_csrf"
CSRF_HEADER = "x-csrf-token"

# `/` serves the SPA shell, which is how the login screen is reached at all, so it cannot itself
# require a session. The data behind it still does - every /api route does.
PUBLIC_EXACT = frozenset({"/", "/login", "/health", "/github/webhook"})
PUBLIC_PREFIXES = ("/assets/", "/auth/", "/oauth/")
MUTATING = frozenset({"POST", "PUT", "PATCH", "DELETE"})


def is_public(path: str) -> bool:
    return path in PUBLIC_EXACT or path.startswith(PUBLIC_PREFIXES)


def check_configuration() -> None:
    """Refuse to start rather than lock everyone out.

    With AUTH_REQUIRED on and LDAP unconfigured, no session could ever be obtained - the login form
    would always say no and there is no way in. Crashing at startup with this message is far easier
    to act on than a running app nobody can enter.
    """
    if not settings.auth_required:
        logger.warning("AUTH_REQUIRED is false: the dashboard is open to anyone who can reach it.")
        return
    missing = []
    if not settings.ldap_server:
        missing.append("LDAP_SERVER")
    if not settings.ldap_base_dn:
        missing.append("LDAP_BASE_DN")
    if not settings.ldap_bind_dn:
        missing.append("LDAP_BIND_DN")
    if missing:
        raise RuntimeError(
            "AUTH_REQUIRED is on but directory sign-in is not configured (missing "
            + ", ".join(missing)
            + "). Set them in .env, or set AUTH_REQUIRED=false to run without sign-in - which is "
              "not safe for anything shared."
        )


# --- request helpers -------------------------------------------------------------------------

def session_from(request: Request) -> dict | None:
    return auth.load_session(request.cookies.get(SESSION_COOKIE))


def require_session(request: Request) -> dict:
    """FastAPI dependency: the signed-in session, or 401."""
    session = session_from(request)
    if not session:
        raise HTTPException(401, "Sign in to continue.")
    return session


def require_admin(request: Request) -> dict:
    session = require_session(request)
    if session.get("role") != auth.ADMIN:
        raise HTTPException(403, "Administrator access is required.")
    return session


def set_session_cookie(response, session_id: str) -> None:
    response.set_cookie(
        SESSION_COOKIE, session_id,
        httponly=True,          # no script may read it
        samesite="lax",         # not strict: the OAuth callback arrives cross-site and would lose it
        secure=settings.session_cookie_secure,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )


def clear_session_cookie(response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


# --- CSRF ------------------------------------------------------------------------------------

def ensure_csrf_cookie(request: Request, response):
    """Give every browser a CSRF token, readable by script so the SPA can echo it back."""
    if request.cookies.get(CSRF_COOKIE):
        return response
    response.set_cookie(
        CSRF_COOKIE, secrets.token_urlsafe(24),
        httponly=False,         # deliberately readable: the double-submit pattern needs it
        samesite="lax",
        secure=settings.session_cookie_secure,
        max_age=settings.session_ttl_hours * 3600,
        path="/",
    )
    return response


def csrf_ok(request: Request) -> bool:
    """Double-submit check.

    The session cookie rides along automatically, so without this a third-party page could drive
    the credential endpoints as the signed-in user. A cross-origin page cannot read the cookie to
    echo it, which is what makes the comparison meaningful. Compared in constant time so the check
    itself leaks nothing.
    """
    cookie = request.cookies.get(CSRF_COOKIE) or ""
    header = request.headers.get(CSRF_HEADER) or ""
    if not cookie or not header:
        return False
    return hmac.compare_digest(cookie, header)


# --- middleware ------------------------------------------------------------------------------

def install(app) -> None:
    @app.middleware("http")
    async def guard(request: Request, call_next):
        path = request.url.path

        if not settings.auth_required or is_public(path):
            # The webhook is exempt by design: GitHub cannot send a CSRF token, and it is already
            # authenticated by its HMAC signature.
            return ensure_csrf_cookie(request, await call_next(request))

        session = session_from(request)
        if not session:
            if path.startswith("/api/"):
                return JSONResponse({"detail": "Sign in to continue."}, status_code=401)
            return RedirectResponse("/login")

        if request.method in MUTATING and not csrf_ok(request):
            return JSONResponse({"detail": "Missing or invalid CSRF token."}, status_code=403)

        request.state.session = session
        if auth.needs_touch(session, auth.now_utc()):
            auth.touch_session(session["id"])
        return ensure_csrf_cookie(request, await call_next(request))
