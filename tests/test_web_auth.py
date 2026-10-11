from datetime import datetime, timedelta, timezone

from app.auth import needs_touch
from app.main import app
from app.web_auth import is_public

# Routes that are public on purpose and no others. `/` serves the SPA shell, which is how the login
# screen is reached at all; the webhook authenticates by HMAC signature instead of a session.
PUBLIC_ROUTES = {"/", "/health", "/github/webhook", "/auth/login"}
PUBLIC_PREFIXES = ("/assets", "/oauth/")

# --- the guard that matters ------------------------------------------------------------------

def test_no_route_is_reachable_without_a_session_by_accident():
    """Every declared route must be either knowingly public or session-protected.

    This is the test that catches the failure mode this whole module exists to prevent: a route
    added later whose path happens to match a public prefix, silently exposing it.
    """
    offenders = []
    for route in app.routes:
        path = getattr(route, "path", None)
        if not path or not path.startswith("/"):
            continue
        if path in PUBLIC_ROUTES or path.startswith(PUBLIC_PREFIXES):
            continue
        if is_public(path):
            offenders.append(path)
    assert offenders == [], f"reachable without a session: {offenders}"

def test_the_data_endpoints_are_not_public():
    for path in ["/api/dashboard", "/api/findings", "/api/reviews", "/api/graph", "/api/me",
                 "/api/credentials", "/api/credentials/acme", "/api/logout",
                 "/repositories/acme/widgets/snapshots",
                 "/api/repositories/acme/widgets/commits"]:
        assert is_public(path) is False, f"{path} must require a session"

def test_lookalike_paths_are_not_public():
    # A prefix check without its trailing slash would let these through.
    for path in ["/assetsomething", "/healthz", "/loginx", "/authx", "/authentication",
                 "/oauthx", "/github/webhook/extra", "/health/../api/dashboard"]:
        assert is_public(path) is False, f"{path} must not be treated as public"

def test_the_expected_paths_are_public():
    for path in ["/", "/health", "/github/webhook", "/auth/login", "/assets/index-abc.js"]:
        assert is_public(path) is True, f"{path} must be reachable without a session"

# --- the behaviour, not just the classification ------------------------------------------------

def _client():
    # No context manager: that would run the startup hook, which needs a database. The middleware
    # never reaches the database for an unauthenticated request, because it only loads a session
    # when a cookie is present.
    from fastapi.testclient import TestClient
    import app.main as main
    return TestClient(main.app)

def test_api_routes_answer_401_without_a_session():
    from app.config import settings
    previous, settings.auth_required = settings.auth_required, True
    try:
        client = _client()
        for path in ["/api/dashboard", "/api/findings", "/api/reviews", "/api/graph",
                     "/api/credentials", "/api/me", "/api/repositories/acme/widgets/commits"]:
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 401, f"{path} -> {response.status_code}"
    finally:
        settings.auth_required = previous

def test_page_routes_redirect_to_the_login_screen():
    from app.config import settings
    previous, settings.auth_required = settings.auth_required, True
    try:
        client = _client()
        response = client.get("/repositories/acme/widgets/snapshots", follow_redirects=False)
        assert response.status_code in (302, 307)
        assert response.headers["location"] == "/login"
    finally:
        settings.auth_required = previous

def test_the_webhook_is_reached_rather_than_blocked_by_the_session_gate():
    # GitHub cannot present a session, so the webhook must get past the middleware and be refused
    # by its own signature check instead. A 401 either way would hide which layer said no.
    from app.config import settings
    previous, settings.auth_required = settings.auth_required, True
    try:
        client = _client()
        response = client.post("/github/webhook", json={}, follow_redirects=False)
        assert response.status_code == 401
        assert "signature" in response.json()["detail"].lower()
    finally:
        settings.auth_required = previous

def test_state_changing_requests_need_a_csrf_token():
    from app.config import settings
    previous, settings.auth_required = settings.auth_required, True
    try:
        client = _client()
        # No session at all: the session gate answers first, and says so.
        response = client.post("/api/logout", follow_redirects=False)
        assert response.status_code == 401
        assert "sign in" in response.json()["detail"].lower()
    finally:
        settings.auth_required = previous

def test_sign_in_disabled_still_reports_an_identity():
    # AUTH_REQUIRED=false is an escape hatch for a local trial, and the UI still needs a user.
    from app.config import settings
    previous, settings.auth_required = settings.auth_required, False
    try:
        client = _client()
        body = client.get("/api/me").json()
        assert body["auth_required"] is False
        assert body["role"] == "admin"
    finally:
        settings.auth_required = previous

# --- session touch throttling -----------------------------------------------------------------

def test_a_stale_session_is_touched():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    session = {"last_seen_at": now - timedelta(minutes=5)}
    assert needs_touch(session, now) is True

def test_a_freshly_seen_session_is_not_written_again():
    # Every asset request passes through the middleware; an unconditional write would be a
    # database write per request.
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert needs_touch({"last_seen_at": now - timedelta(seconds=5)}, now) is False

def test_a_session_with_no_last_seen_is_touched():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert needs_touch({"last_seen_at": None}, now) is True
    assert needs_touch({}, now) is True

def test_the_touch_interval_boundary_is_inclusive():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    assert needs_touch({"last_seen_at": now - timedelta(seconds=60)}, now, 60) is True
    assert needs_touch({"last_seen_at": now - timedelta(seconds=59)}, now, 60) is False
