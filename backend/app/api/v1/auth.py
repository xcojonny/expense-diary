import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import REFRESH_COOKIE
from app.core.config import get_settings
from app.db.session import get_db
from app.models import User
from app.schemas.auth import AuthConfigOut, MagicLinkRequest, SessionOut, TokenRequest
from app.services import auth_service, group_service, oidc_service

router = APIRouter(prefix="/auth", tags=["auth"])

_OIDC_STATE_COOKIE = "oidc_state"
_COOKIE_PATH = "/api/v1/auth"


def _set_refresh_cookie(response: Response, raw: str) -> None:
    settings = get_settings()
    response.set_cookie(
        REFRESH_COOKIE,
        raw,
        max_age=settings.refresh_token_ttl_days * 86400,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
    )


async def _login(session: AsyncSession, user: User, response: Response) -> SessionOut:
    access, raw = await auth_service.issue_session(session, user)
    _set_refresh_cookie(response, raw)
    return SessionOut(access_token=access)


@router.get("/config", response_model=AuthConfigOut)
async def config() -> AuthConfigOut:
    settings = get_settings()
    return AuthConfigOut(
        oidc_enabled=oidc_service.oidc_enabled(),
        oidc_provider_name=settings.oidc_provider_name,
    )


@router.post("/magic-link", status_code=202)
async def request_magic_link(
    data: MagicLinkRequest, db: AsyncSession = Depends(get_db)
) -> dict[str, str]:
    # Always 202 — never reveal whether the address has an account.
    await auth_service.request_magic_link(db, str(data.email))
    return {"status": "accepted"}


@router.post("/verify", response_model=SessionOut)
async def verify(
    data: TokenRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> SessionOut:
    user = await auth_service.verify_magic_link(db, data.token)
    if user is None:
        raise HTTPException(status_code=400, detail="Link ungültig oder abgelaufen.")
    return await _login(db, user, response)


@router.post("/invitations/accept", response_model=SessionOut)
async def accept_invitation(
    data: TokenRequest, response: Response, db: AsyncSession = Depends(get_db)
) -> SessionOut:
    user = await group_service.accept_invitation(db, data.token)
    if user is None:
        raise HTTPException(status_code=400, detail="Einladung ungültig oder abgelaufen.")
    return await _login(db, user, response)


@router.post("/refresh", response_model=SessionOut)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> SessionOut:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="Keine Sitzung.")
    rotated = await auth_service.rotate_refresh(db, raw)
    if rotated is None:
        raise HTTPException(status_code=401, detail="Sitzung abgelaufen.")
    access, new_raw = rotated
    _set_refresh_cookie(response, new_raw)
    return SessionOut(access_token=access)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        await auth_service.revoke_refresh(db, raw)
    response.delete_cookie(REFRESH_COOKIE, path=_COOKIE_PATH)


# -- OIDC (Authelia) ----------------------------------------------------------


@router.get("/oidc/login")
async def oidc_login() -> RedirectResponse:
    if not oidc_service.oidc_enabled():
        raise HTTPException(status_code=404, detail="SSO ist nicht konfiguriert.")
    state = secrets.token_urlsafe(24)
    url = await oidc_service.authorize_url(state)
    response = RedirectResponse(url, status_code=307)
    response.set_cookie(
        _OIDC_STATE_COOKIE,
        state,
        max_age=600,
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
        path=_COOKIE_PATH,
    )
    return response


@router.get("/oidc/callback")
async def oidc_callback(
    request: Request,
    code: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    settings = get_settings()
    expected = request.cookies.get(_OIDC_STATE_COOKIE)
    if not oidc_service.oidc_enabled() or not code or not state or state != expected:
        return RedirectResponse(f"{settings.base_url}/login?error=sso", status_code=307)
    try:
        info = await oidc_service.exchange(code)
        user = await auth_service.upsert_oidc_user(
            db,
            issuer=info["issuer"],
            subject=info["subject"],
            email=info["email"],
            display_name=info["display_name"],
        )
        _access, raw = await auth_service.issue_session(db, user)
    except Exception:
        return RedirectResponse(f"{settings.base_url}/login?error=sso", status_code=307)
    # Set the refresh cookie and bounce to the frontend, which bootstraps an
    # access token via /auth/refresh.
    response = RedirectResponse(f"{settings.base_url}/login?sso=ok", status_code=307)
    _set_refresh_cookie(response, raw)
    response.delete_cookie(_OIDC_STATE_COOKIE, path=_COOKIE_PATH)
    return response
