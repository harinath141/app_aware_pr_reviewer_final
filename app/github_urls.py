"""URL derivation for github.com and GitHub Enterprise Server.

Deliberately imports nothing from app.config, so it stays importable and unit-testable with no
environment set up - the same property app/crypto.py keeps, and for the same reason.

The trap this module exists to contain: on Enterprise the REST API lives under /api/v3 but
**GraphQL does not** - it is served from /api/graphql at the host root. Concatenating /graphql onto
the REST base silently produces /api/v3/graphql, which 404s, and thread resolution would fail while
every other call kept working.
"""

PUBLIC_API = "https://api.github.com"
PUBLIC_WEB = "https://github.com"
ENTERPRISE_REST_SUFFIX = "/api/v3"


def normalize(url: str | None) -> str:
    return (url or "").strip().rstrip("/")


def rest_base(api_url: str | None) -> str:
    """The REST API root. Blank means github.com."""
    return normalize(api_url) or PUBLIC_API


def web_host(api_url: str | None) -> str:
    """The host serving the web UI and the OAuth endpoints.

    github.com splits the two: the API is api.github.com while OAuth and the UI are github.com.
    Enterprise serves both from one host, with REST tucked under /api/v3.
    """
    base = rest_base(api_url)
    if base == PUBLIC_API:
        return PUBLIC_WEB
    if base.endswith(ENTERPRISE_REST_SUFFIX):
        return base[: -len(ENTERPRISE_REST_SUFFIX)]
    return base


def graphql_url(api_url: str | None, explicit: str | None = None) -> str:
    """The GraphQL endpoint. An explicit override always wins."""
    override = normalize(explicit)
    if override:
        return override
    base = rest_base(api_url)
    if base == PUBLIC_API:
        return f"{PUBLIC_API}/graphql"
    # Not under the REST base: Enterprise serves GraphQL at the host root.
    return f"{web_host(base)}/api/graphql"


def oauth_urls(api_url: str | None) -> tuple[str, str]:
    """(authorize_url, token_url) for the OAuth dance."""
    host = web_host(api_url)
    return f"{host}/login/oauth/authorize", f"{host}/login/oauth/access_token"
