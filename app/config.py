from pydantic_settings import BaseSettings, SettingsConfigDict

from app.github_urls import graphql_url as _graphql_url, oauth_urls as _oauth_urls, web_host

class Settings(BaseSettings):
    github_webhook_secret: str
    github_token: str
    # Fernet key encrypting per-owner tokens stored through the settings page. Optional so the app
    # still boots without it; credential WRITES are refused while it is unset. An empty string in
    # .env is treated as unset.
    github_credential_key: str | None = None
    # Optional gate on the credential settings routes. When set, mutations require a matching
    # X-Admin-Token header. Superseded by requiring an admin session once AUTH_REQUIRED is on.
    github_settings_admin_token: str | None = None
    llm_api_key: str
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4.1-mini"
    # How to force JSON output from the chat model. Provider-dependent:
    #   json_object - OpenAI, DeepSeek, most OpenAI-compatible servers (default)
    #   json_schema - stricter; required by LM Studio, which rejects json_object
    #   none        - prompt-only; relies on parse_review() to recover the JSON
    llm_response_format: str = "json_object"
    embedding_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dimensions: int = 1536
    database_url: str = "postgresql://reviewer:change-me@localhost:5432/reviewer"
    max_archive_bytes: int = 50_000_000
    max_files: int = 12_000
    max_file_bytes: int = 500_000
    max_chunk_chars: int = 3500
    max_context_chunks: int = 12
    max_diff_chars: int = 40_000

    # --- GitHub Enterprise Server -------------------------------------------------------------
    # Blank means github.com. On GHES this is https://<host>/api/v3 - see app/github_urls.py for
    # why GraphQL and OAuth are NOT derived by appending to this.
    github_api_url: str = ""
    github_graphql_url: str = ""
    # Public base URL of this app, used to build the webhook payload URL shown during onboarding.
    public_base_url: str = ""

    # --- GitHub OAuth (per-user repository visibility) ----------------------------------------
    # Unset means "Connect GitHub" is unavailable and users see only repositories they onboarded.
    oauth_client_id: str = ""
    oauth_client_secret: str = ""
    oauth_callback_url: str = ""

    # --- Authentication ------------------------------------------------------------------------
    # Secure by default. With this on, every route except /health, /github/webhook, the login and
    # OAuth routes and /assets requires a session. Set AUTH_REQUIRED=false only for a local trial;
    # startup refuses to begin if it is on and LDAP is not configured, so a missing setting is a
    # loud crash rather than a silent lockout.
    auth_required: bool = True
    session_ttl_hours: int = 12
    # Off only for plain-HTTP local testing: a Secure cookie is never sent over http.
    session_cookie_secure: bool = True

    # --- LDAP ----------------------------------------------------------------------------------
    ldap_server: str = ""
    ldap_base_dn: str = ""
    # Service account used to find the user entry; the user's own password is then verified by
    # re-binding as the DN that search returned.
    ldap_bind_dn: str = ""
    ldap_bind_password: str = ""
    # Which attribute the typed username is matched against: sAMAccountName (AD default) or
    # userPrincipalName / uid on other directories.
    ldap_user_attribute: str = "sAMAccountName"
    ldap_admin_group: str = "CONTEXTGUARD-ADMIN"
    ldap_user_group: str = "CONTEXTGUARD-USER"
    ldap_timeout_seconds: int = 10

    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    @property
    def api_root(self) -> str:
        return self.github_api_url or "https://api.github.com"

    @property
    def graphql_endpoint(self) -> str:
        return _graphql_url(self.github_api_url, self.github_graphql_url)

    @property
    def web_root(self) -> str:
        return web_host(self.github_api_url)

    @property
    def oauth_endpoints(self) -> tuple[str, str]:
        return _oauth_urls(self.github_api_url)

    @property
    def ldap_configured(self) -> bool:
        return bool(self.ldap_server and self.ldap_base_dn and self.ldap_bind_dn)

    @property
    def oauth_configured(self) -> bool:
        return bool(self.oauth_client_id and self.oauth_client_secret)

settings = Settings()
