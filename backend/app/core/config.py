from functools import lru_cache

from pydantic import EmailStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All runtime configuration, sourced exclusively from the environment.

    The LLM block is provider-agnostic on purpose: the receipt-extraction
    pipeline talks to an adapter (see integrations/llm), so switching from an
    OpenAI-Vision-compatible endpoint to a local Ollama is a config change, not
    a code change.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "production"  # production | development | test
    base_url: str = "http://localhost:3000"  # public URL of the frontend (links in mail)
    api_base_url: str = "http://localhost:8000"  # public URL of the API (OIDC redirect)

    secret_key: str = "change-me"  # JWT signing (set a strong value in prod)

    database_url: str = "postgresql+asyncpg://expense:expense@localhost:5432/expense"
    redis_url: str = "redis://localhost:6379/0"

    # Uploaded receipt images / PDFs. Relative default targets non-Docker local
    # dev; the Docker image mounts /data/media instead.
    media_dir: str = "./.data/media"

    default_locale: str = "de"

    # -- Tenancy & auth --------------------------------------------------------
    # The initial admin is bootstrapped on startup (active instance admin, owns
    # a default group). Further users arrive via group invitation or OIDC.
    default_group_name: str = "Haushalt"
    initial_admin_email: EmailStr | None = None

    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30  # idle lifetime; every rotation extends it
    refresh_reuse_grace_seconds: int = 60  # parallel-tab rotation race ≠ theft
    magic_link_ttl_minutes: int = 15
    magic_link_replay_grace_seconds: int = 120  # bound browser re-loading its own link
    magic_link_code_attempts: int = 5  # wrong pairing codes per token before it burns
    invitation_ttl_days: int = 14
    cookie_secure: bool = True  # set false for plain-HTTP local dev

    # Rate limits (Redis-backed, fixed window; fail open if Redis is down)
    magic_link_per_email: int = 5  # per 15 minutes
    magic_link_per_ip: int = 10  # per hour
    login_code_per_ip: int = 20  # pairing-code attempts per 15 minutes

    # -- SMTP (magic-link / invitation mail) -----------------------------------
    # With no host configured the mailer logs the link instead of sending — fine
    # for local dev (grab the link from the backend log).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_starttls: bool = True
    mail_from: str = "haushaltsbuch@example.org"
    mail_from_name: str = "Haushaltsbuch"

    # -- OIDC single sign-on (Authelia or any OIDC provider) -------------------
    # Empty issuer disables the SSO button. Discovery document is fetched from
    # {issuer}/.well-known/openid-configuration.
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_provider_name: str = "Authelia"  # login-button label
    oidc_scopes: str = "openid email profile"

    # -- Upload hardening ------------------------------------------------------
    upload_max_bytes: int = 15 * 1024 * 1024  # 15 MiB per receipt file
    upload_allowed_types: tuple[str, ...] = (
        "image/jpeg",
        "image/png",
        "image/webp",
        "application/pdf",
    )

    # -- LLM (vision extraction) — provider-agnostic adapter -------------------
    # "none" enables the rule-based/no-op fallback so the app runs without any
    # LLM configured (receipts land in needs_review instead of done).
    llm_provider: str = "none"  # none | openai | ollama
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"  # OpenAI-Vision-compatible or Ollama endpoint
    llm_model: str = "gpt-4o-mini"
    llm_timeout_seconds: float = 90.0

    # Git-SHA of the running image, baked in at build time. Empty in local dev.
    git_sha: str = ""

    @property
    def is_dev(self) -> bool:
        return self.app_env != "production"


@lru_cache
def get_settings() -> Settings:
    return Settings()
