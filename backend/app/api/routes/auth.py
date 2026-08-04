"""Login, Logout, Sessionstatus (ADR-004)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status

from app.api.deps import SessionDep, SettingsDep
from app.core.config import AuthMode, Settings
from app.core.logging import get_logger
from app.core.security import (
    RateLimiter,
    create_session_token,
    read_session_token,
    verify_password,
)
from app.schemas import LoginRequest, SessionInfo

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)

# Prozesslokal — bei einem Prozess wirkungsgleich zum Redis-Zähler von früher.
_login_limiter: RateLimiter | None = None


def _limiter(settings: Settings) -> RateLimiter:
    global _login_limiter
    if _login_limiter is None:
        _login_limiter = RateLimiter(
            limit=settings.login_max_attempts,
            window_seconds=settings.login_window_seconds,
        )
    return _login_limiter


def reset_login_limiter() -> None:
    """Nur für Tests."""
    global _login_limiter
    _login_limiter = None


def _client_key(request: Request) -> str:
    return request.client.host if request.client else "unknown"


@router.get("/session", response_model=SessionInfo)
async def read_session(request: Request, settings: SettingsDep) -> SessionInfo:
    """Ob diese Anfrage angemeldet ist — ohne 401, damit die SPA beim Start
    entscheiden kann, ob sie die Anmeldemaske zeigt."""
    if settings.auth_mode is AuthMode.NONE:
        return SessionInfo(
            authenticated=True, auth_mode=settings.auth_mode.value, login_required=False
        )

    if settings.auth_mode is AuthMode.TRUSTED_HEADER:
        user = request.headers.get(settings.auth_trusted_header, "").strip()
        return SessionInfo(
            authenticated=bool(user), auth_mode=settings.auth_mode.value, login_required=False
        )

    cookie = request.cookies.get(settings.cookie_name) or ""
    authenticated = (
        bool(cookie) and read_session_token(cookie, secret=settings.session_secret) is not None
    )
    return SessionInfo(
        authenticated=authenticated, auth_mode=settings.auth_mode.value, login_required=True
    )


@router.post("/login", response_model=SessionInfo)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    _session: SessionDep,
) -> SessionInfo:
    if settings.auth_mode is not AuthMode.PASSWORD:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AUTH_MODE={settings.auth_mode.value} kennt keinen Passwort-Login.",
        )

    if not _limiter(settings).check(_client_key(request)):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Zu viele Versuche. Bitte später erneut probieren.",
        )

    if not verify_password(payload.password, settings.auth_password):
        log.warning("auth.login_failed", extra={"client": _client_key(request)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Passwort stimmt nicht."
        )

    token = create_session_token(
        "haushalt",
        secret=settings.session_secret,
        ttl_seconds=settings.session_ttl_hours * 3600,
    )
    response.set_cookie(
        settings.cookie_name,
        token,
        max_age=settings.session_ttl_hours * 3600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    log.info("auth.login_ok")
    return SessionInfo(authenticated=True, auth_mode=settings.auth_mode.value, login_required=True)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, settings: SettingsDep) -> None:
    response.delete_cookie(settings.cookie_name, path="/")
