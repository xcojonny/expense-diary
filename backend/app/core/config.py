from functools import lru_cache

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
    base_url: str = "http://localhost:3000"  # public URL of the frontend

    database_url: str = "postgresql+asyncpg://expense:expense@localhost:5432/expense"
    redis_url: str = "redis://localhost:6379/0"

    # Uploaded receipt images / PDFs. Relative default targets non-Docker local
    # dev; the Docker image mounts /data/media instead.
    media_dir: str = "./.data/media"

    default_locale: str = "de"

    # Tenancy. Real multi-group support (auth + membership) comes later; until
    # then every receipt belongs to this bootstrapped default group, so the
    # group_id columns and the current-group seam already carry it. See
    # docs/architecture.md §6.
    default_group_name: str = "Haushalt"

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
