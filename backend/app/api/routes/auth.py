"""Anmeldung: Passwort, OIDC, Proxy-Header — plus Einladung einlösen (ADR-004)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    HOUSEHOLD_COOKIE,
    SessionDep,
    SettingsDep,
    UserDep,
    require_user,
)
from app.core.config import AuthMode, Settings
from app.core.logging import get_logger
from app.core.security import (
    RateLimiter,
    create_session_token,
    read_session_token,
    verify_password,
)
from app.integrations.oidc import OidcError, build_oidc_client
from app.models import HouseholdMember, User
from app.schemas import InvitationAccept, LoginRequest, MembershipOut, SessionInfo, UserOut
from app.services import households as households_service
from app.services import users as users_service

router = APIRouter(prefix="/auth", tags=["auth"])
log = get_logger(__name__)

OIDC_STATE_COOKIE = "eb_oidc_state"
OIDC_STATE_TTL_SECONDS = 600

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


def _set_session_cookie(response: Response, settings: Settings, user: User) -> None:
    token = create_session_token(
        f"user:{user.id}",
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


def _user_out(user: User, memberships: list[HouseholdMember]) -> UserOut:
    return UserOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        memberships=[
            MembershipOut(
                household_id=member.household_id,
                household_name=member.household.name,
                role=member.role,
            )
            for member in memberships
        ],
    )


async def session_info(
    session: AsyncSession, settings: Settings, user: User | None
) -> SessionInfo:
    """Sessionantwort bauen — inklusive Haushalte und aktivem Haushalt."""
    memberships = (
        await households_service.memberships_for(session, user.id) if user is not None else []
    )
    return SessionInfo(
        authenticated=user is not None,
        auth_mode=settings.auth_mode.value,
        login_required=settings.auth_mode is AuthMode.PASSWORD,
        multi_user=settings.auth_mode.is_multi_user,
        sso_available=settings.auth_mode is AuthMode.OIDC and settings.oidc_configured,
        user=_user_out(user, memberships) if user is not None else None,
        active_household_id=memberships[0].household_id if memberships else None,
    )


@router.get("/session", response_model=SessionInfo)
async def read_session(request: Request, settings: SettingsDep, session: SessionDep) -> SessionInfo:
    """Ob diese Anfrage angemeldet ist — **ohne** 401, damit die SPA beim Start
    entscheiden kann, ob sie die Anmeldemaske zeigt."""
    try:
        user = await require_user(request, settings, session)
    except HTTPException:
        return await session_info(session, settings, None)

    info = await session_info(session, settings, user)

    # Ein gültiges Auswahl-Cookie übersteuert den Default.
    requested = request.cookies.get(HOUSEHOLD_COOKIE)
    if requested and requested.isdigit():
        member = await households_service.membership(
            session, household_id=int(requested), user_id=user.id
        )
        if member is not None:
            info.active_household_id = member.household_id
    return info


# --- Passwort (Einzelnutzer) --------------------------------------------------


@router.post("/login", response_model=SessionInfo)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
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

    user = await users_service.ensure_single_user(session, settings)
    await session.commit()
    _set_session_cookie(response, settings, user)
    log.info("auth.login_ok", extra={"user_id": user.id})
    return await session_info(session, settings, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(response: Response, settings: SettingsDep) -> None:
    response.delete_cookie(settings.cookie_name, path="/")
    response.delete_cookie(HOUSEHOLD_COOKIE, path="/")


# --- OIDC (Mehrbenutzer) ------------------------------------------------------


@router.get("/oidc/login")
async def oidc_login(response: Response, settings: SettingsDep) -> RedirectResponse:
    """Zum Identity Provider umleiten. `state` liegt als kurzlebiges Cookie
    daneben und wird im Callback verglichen (CSRF-Schutz)."""
    if settings.auth_mode is not AuthMode.OIDC:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"AUTH_MODE={settings.auth_mode.value} kennt keinen SSO-Login.",
        )
    client = build_oidc_client(settings)
    if not client.configured:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC ist nicht vollständig konfiguriert.",
        )

    state = client.new_state()
    try:
        url = await client.authorization_url(state=state)
    except OidcError as exc:
        log.warning("oidc.login_failed", extra={"error": str(exc)})
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc)
        ) from exc

    redirect = RedirectResponse(url, status_code=status.HTTP_307_TEMPORARY_REDIRECT)
    redirect.set_cookie(
        OIDC_STATE_COOKIE,
        state,
        max_age=OIDC_STATE_TTL_SECONDS,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return redirect


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    settings: SettingsDep,
    session: SessionDep,
    code: str = "",
    state: str = "",
    error: str = "",
) -> RedirectResponse:
    """Rückkanal vom Identity Provider: Code tauschen, Nutzer anlegen/finden,
    Session setzen und zur App zurückleiten."""
    if settings.auth_mode is not AuthMode.OIDC:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SSO ist aus.")

    def back(message: str) -> RedirectResponse:
        """Fehler gehen an die Login-Seite — der Browser landet nie auf JSON."""
        log.warning("oidc.callback_failed", extra={"error": message})
        target = f"{settings.base_url.rstrip('/')}/login?sso_error={message[:200]}"
        redirect = RedirectResponse(target, status_code=status.HTTP_303_SEE_OTHER)
        redirect.delete_cookie(OIDC_STATE_COOKIE, path="/")
        return redirect

    if error:
        return back(f"Der Identity Provider meldet: {error}")

    expected = request.cookies.get(OIDC_STATE_COOKIE, "")
    # Konstante Laufzeit, und ein leerer erwarteter Wert darf nie durchgehen.
    if not expected or not state or not verify_password(state, expected):
        return back("Der Anmeldevorgang ist abgelaufen. Bitte erneut versuchen.")
    if not code:
        return back("Der Identity Provider hat keinen Code geliefert.")

    try:
        identity = await build_oidc_client(settings).exchange(code=code)
        user = await users_service.upsert_oidc_user(
            session,
            issuer=identity.issuer,
            subject=identity.subject,
            email=identity.email,
            display_name=identity.display_name,
        )
        if not user.is_active:
            return back("Dieser Zugang ist deaktiviert.")
        await users_service.ensure_personal_household(session, user)
        await session.commit()
    except (OidcError, ValueError) as exc:
        await session.rollback()
        return back(str(exc))

    log.info("auth.oidc_ok", extra={"user_id": user.id})
    redirect = RedirectResponse(
        settings.base_url.rstrip("/") + "/", status_code=status.HTTP_303_SEE_OTHER
    )
    redirect.delete_cookie(OIDC_STATE_COOKIE, path="/")
    _set_session_cookie(redirect, settings, user)
    return redirect


# --- Einladung einlösen -------------------------------------------------------


@router.post("/invitations/accept", response_model=SessionInfo)
async def accept_invitation(
    payload: InvitationAccept,
    response: Response,
    settings: SettingsDep,
    session: SessionDep,
    user: UserDep,
) -> SessionInfo:
    """Einladung des **angemeldeten** Nutzers einlösen.

    Anmeldung zuerst, Beitritt danach: so hängt der Beitritt nicht daran, dass
    der Identity Provider dieselbe Mailadresse liefert wie die Einladung.
    """
    try:
        member = await households_service.accept_invitation(session, token=payload.token, user=user)
    except households_service.HouseholdError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    await session.commit()
    log.info(
        "invitation.accepted",
        extra={"user_id": user.id, "household_id": member.household_id},
    )

    # Direkt in den neuen Haushalt wechseln — das ist, was man erwartet.
    response.set_cookie(
        HOUSEHOLD_COOKIE,
        str(member.household_id),
        max_age=settings.session_ttl_hours * 3600,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    info = await session_info(session, settings, user)
    info.active_household_id = member.household_id
    return info


__all__ = ["read_session_token", "reset_login_limiter", "router"]
