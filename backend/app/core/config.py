"""Konfiguration — eine flache, dokumentierte ENV-Liste.

Jede Einstellung hat einen Default, mit dem die App lokal sofort startet.
Produktionsrelevante Pflichtwerte prüft `validate_for_production()` beim Start.
"""

from __future__ import annotations

import secrets
from enum import StrEnum
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Fallback-Secret für Entwicklung: prozessweit stabil, aber nicht persistent —
# nach einem Neustart sind Sessions ungültig. In Produktion blockt
# validate_for_production(), wenn SECRET_KEY fehlt.
_DEV_SECRET = secrets.token_urlsafe(48)


class AuthMode(StrEnum):
    """Siehe ADR-004.

    `PASSWORD` und `NONE` sind Einzelnutzer-Modi (ein Haushalt, ein impliziter
    Nutzer). `OIDC` und `TRUSTED_HEADER` sind mehrbenutzerfähig — nur dort gibt
    es Einladungen und mehrere Haushalte.
    """

    PASSWORD = "password"
    OIDC = "oidc"
    TRUSTED_HEADER = "trusted_header"
    NONE = "none"

    @property
    def is_multi_user(self) -> bool:
        return self in (AuthMode.OIDC, AuthMode.TRUSTED_HEADER)


class LlmProvider(StrEnum):
    NONE = "none"
    OPENAI = "openai"
    OPENROUTER = "openrouter"
    OLLAMA = "ollama"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    app_env: str = "development"
    log_level: str = "INFO"
    log_format: str = "text"  # text | json

    # --- Ablage ---------------------------------------------------------------
    # Alles Zustandsbehaftete liegt unter DATA_DIR: die SQLite-Datei und die
    # hochgeladenen Belege. Ein Volume genügt damit für ein Backup.
    data_dir: Path = Path("./data")
    # Leer → aus data_dir abgeleitet (siehe `sqlalchemy_url`).
    database_url: str = ""

    # --- Auth (ADR-004) -------------------------------------------------------
    auth_mode: AuthMode = AuthMode.PASSWORD
    auth_password: str = ""
    # Nur in AUTH_MODE=trusted_header: Header, den der Reverse Proxy setzt.
    # ACHTUNG: Der Proxy MUSS diesen Header überschreiben, sonst kann ihn jeder
    # Client selbst mitschicken.
    auth_trusted_header: str = "Remote-User"
    # Nur in AUTH_MODE=trusted_header: optionale Header für Anzeigename und
    # E-Mail, falls der Proxy sie mitliefert.
    auth_trusted_email_header: str = "Remote-Email"
    auth_trusted_name_header: str = "Remote-Name"
    secret_key: str = ""  # leer → Zufallswert (Dev); Sessions überleben keinen Neustart
    session_ttl_hours: int = 24 * 30
    cookie_secure: bool = False
    cookie_name: str = "eb_session"
    # Fehlversuche pro Fenster, prozesslokal (ein Prozess — ADR-002).
    login_max_attempts: int = 10
    login_window_seconds: int = 300

    # --- Upload ---------------------------------------------------------------
    upload_max_bytes: int = 15 * 1024 * 1024

    # --- LLM (ADR: provider-agnostischer Adapter) -----------------------------
    llm_provider: LlmProvider = LlmProvider.NONE
    llm_base_url: str = ""
    llm_api_key: str = ""
    llm_model: str = ""
    llm_timeout_seconds: float = 120.0
    # Fotos werden vor dem Versand auf diese Kantenlänge verkleinert — spart
    # Tokens und Zeit, ohne dass ein Bon unleserlich wird.
    llm_max_image_px: int = 1600

    # --- Worker (ADR-002) -----------------------------------------------------
    worker_enabled: bool = True
    worker_max_attempts: int = 3
    worker_idle_seconds: float = 5.0

    # --- OIDC (AUTH_MODE=oidc) ------------------------------------------------
    # Der Issuer wird per Discovery aufgelöst (`/.well-known/openid-configuration`).
    oidc_issuer: str = ""
    oidc_client_id: str = ""
    oidc_client_secret: str = ""
    oidc_scopes: str = "openid email profile"
    # Öffentliche Basis-URL der Instanz — daraus entsteht die Redirect-URI, die
    # beim Identity Provider hinterlegt sein muss.
    base_url: str = "http://localhost:8000"

    # --- Mail (für Einladungen) -----------------------------------------------
    # Ohne SMTP_HOST wird der Einladungslink ins Log geschrieben statt versendet.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "haushaltsbuch@localhost"
    smtp_starttls: bool = True

    invitation_ttl_hours: int = 168  # 7 Tage

    currency: str = "EUR"

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite+aiosqlite:///{(self.data_dir / 'haushalt.db').as_posix()}"

    @property
    def session_secret(self) -> str:
        return self.secret_key or _DEV_SECRET

    @property
    def oidc_redirect_uri(self) -> str:
        return f"{self.base_url.rstrip('/')}/api/auth/oidc/callback"

    @property
    def oidc_configured(self) -> bool:
        return bool(self.oidc_issuer and self.oidc_client_id and self.oidc_client_secret)

    @property
    def mail_configured(self) -> bool:
        return bool(self.smtp_host)

    @property
    def media_dir(self) -> Path:
        return self.data_dir / "belege"

    def validate_for_production(self) -> list[str]:
        """Liefert blockierende Konfigurationsfehler (leer = alles gut)."""
        problems: list[str] = []
        if not self.is_production:
            return problems
        if not self.secret_key:
            problems.append("SECRET_KEY fehlt — Sessions überleben keinen Neustart.")
        elif len(self.secret_key) < 32:
            problems.append("SECRET_KEY ist kürzer als 32 Zeichen.")
        if self.auth_mode is AuthMode.PASSWORD and not self.auth_password:
            problems.append("AUTH_MODE=password, aber AUTH_PASSWORD ist leer.")
        if self.auth_mode is AuthMode.OIDC and not self.oidc_configured:
            problems.append(
                "AUTH_MODE=oidc, aber OIDC_ISSUER, OIDC_CLIENT_ID oder "
                "OIDC_CLIENT_SECRET fehlt — niemand kann sich anmelden."
            )
        if self.auth_mode is AuthMode.NONE:
            problems.append(
                "AUTH_MODE=none in Produktion — die Instanz ist ungeschützt. "
                "password oder trusted_header verwenden."
            )
        if not self.cookie_secure and self.auth_mode is not AuthMode.TRUSTED_HEADER:
            problems.append("COOKIE_SECURE=false in Produktion (HTTPS erwartet).")
        return problems


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Nur für Tests: erzwingt Neuladen der Settings."""
    get_settings.cache_clear()


__all__ = [
    "AuthMode",
    "LlmProvider",
    "Settings",
    "get_settings",
    "reset_settings_cache",
]
