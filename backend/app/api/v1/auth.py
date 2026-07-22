import secrets

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import REFRESH_COOKIE, client_ip, get_limiter
from app.core.config import get_settings
from app.core.ratelimit import RateLimiter
from app.core.security import format_login_code
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    AuthConfigOut,
    CodeRequest,
    LoginStatusResponse,
    MagicLinkRequest,
    SessionOut,
    TokenRequest,
    VerifyResponse,
)
from app.services import auth_service, group_service, magic_link_service, oidc_service
from app.services.magic_link_service import VerificationError

router = APIRouter(prefix="/auth", tags=["auth"])

_OIDC_STATE_COOKIE = "oidc_state"
_LOGIN_REQUEST_COOKIE = "login_request"  # stable per-browser secret (magic-link binding)
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


def _ensure_login_request(request: Request, response: Response) -> str:
    """Return the requesting browser's stable secret, minting + setting the
    httpOnly cookie if absent. Only its hash is stored on the token."""
    secret = request.cookies.get(_LOGIN_REQUEST_COOKIE)
    if not secret:
        secret = secrets.token_urlsafe(32)
        response.set_cookie(
            _LOGIN_REQUEST_COOKIE,
            secret,
            max_age=400 * 86400,
            httponly=True,
            secure=get_settings().cookie_secure,
            samesite="lax",
            path=_COOKIE_PATH,
        )
    return secret


async def _issue(session: AsyncSession, user: User, request: Request, response: Response) -> str:
    access, raw = await auth_service.issue_session(
        session, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
    )
    _set_refresh_cookie(response, raw)
    return access


@router.get("/config", response_model=AuthConfigOut)
async def config() -> AuthConfigOut:
    settings = get_settings()
    return AuthConfigOut(
        oidc_enabled=oidc_service.oidc_enabled(),
        oidc_provider_name=settings.oidc_provider_name,
    )


@router.post("/magic-link", status_code=202)
async def request_magic_link(
    data: MagicLinkRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_limiter),
) -> dict[str, str]:
    # Always 202 — never reveal whether the address has an account.
    secret = _ensure_login_request(request, response)
    await magic_link_service.request_login_link(
        db, limiter, email=str(data.email), ip=client_ip(request), requester_secret=secret
    )
    return {"status": "accepted"}


@router.post("/verify", response_model=VerifyResponse)
async def verify(
    data: TokenRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> VerifyResponse:
    secret = request.cookies.get(_LOGIN_REQUEST_COOKIE)
    try:
        result = await magic_link_service.verify(db, data.token, requester_secret=secret)
    except VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result.user is not None:
        access = await _issue(db, result.user, request, response)
        return VerifyResponse(status="session", access_token=access)
    # Opened in a different browser → show the pairing code there.
    return VerifyResponse(status="code", code=format_login_code(result.code or ""))


@router.post("/login-status", response_model=LoginStatusResponse)
async def login_status(
    request: Request, db: AsyncSession = Depends(get_db)
) -> LoginStatusResponse:
    secret = request.cookies.get(_LOGIN_REQUEST_COOKIE)
    if not secret:
        return LoginStatusResponse(status="pending")
    status = await magic_link_service.login_status(db, requester_secret=secret)
    return LoginStatusResponse(status=status)


@router.post("/verify-code", response_model=SessionOut)
async def verify_code(
    data: CodeRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
    limiter: RateLimiter = Depends(get_limiter),
) -> SessionOut:
    secret = request.cookies.get(_LOGIN_REQUEST_COOKIE)
    if not secret:
        raise HTTPException(status_code=400, detail="Kein Anmeldevorgang in diesem Browser.")
    if not await limiter.hit(
        f"code:ip:{client_ip(request) or 'none'}", get_settings().login_code_per_ip, 900
    ):
        raise HTTPException(status_code=429, detail="Zu viele Versuche. Bitte später erneut.")
    try:
        user = await magic_link_service.verify_code(db, code=data.code, requester_secret=secret)
    except VerificationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return SessionOut(access_token=await _issue(db, user, request, response))


@router.post("/invitations/accept", response_model=SessionOut)
async def accept_invitation(
    data: TokenRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> SessionOut:
    user = await group_service.accept_invitation(db, data.token)
    if user is None:
        raise HTTPException(status_code=400, detail="Einladung ungültig oder abgelaufen.")
    return SessionOut(access_token=await _issue(db, user, request, response))


@router.post("/refresh", response_model=SessionOut)
async def refresh(
    request: Request, response: Response, db: AsyncSession = Depends(get_db)
) -> SessionOut:
    raw = request.cookies.get(REFRESH_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="Keine Sitzung.")
    rotated = await auth_service.rotate_refresh_token(
        db, raw, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
    )
    if rotated is None:
        response.delete_cookie(REFRESH_COOKIE, path=_COOKIE_PATH)
        raise HTTPException(status_code=401, detail="Sitzung abgelaufen.")
    access, new_raw = rotated
    _set_refresh_cookie(response, new_raw)
    return SessionOut(access_token=access)


@router.post("/logout", status_code=204)
async def logout(request: Request, response: Response, db: AsyncSession = Depends(get_db)) -> None:
    raw = request.cookies.get(REFRESH_COOKIE)
    if raw:
        await auth_service.revoke_refresh_token(db, raw)
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
        _access, raw = await auth_service.issue_session(
            db, user, user_agent=request.headers.get("user-agent"), ip=client_ip(request)
        )
    except Exception:
        return RedirectResponse(f"{settings.base_url}/login?error=sso", status_code=307)
    response = RedirectResponse(f"{settings.base_url}/login?sso=ok", status_code=307)
    _set_refresh_cookie(response, raw)
    response.delete_cookie(_OIDC_STATE_COOKIE, path=_COOKIE_PATH)
    return response
