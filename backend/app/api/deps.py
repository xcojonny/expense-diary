import uuid

import jwt
from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ratelimit import RateLimiter
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models import User
from app.services import group_service

REFRESH_COOKIE = "refresh_token"


def get_limiter(request: Request) -> RateLimiter:
    return RateLimiter(getattr(request.app.state, "redis", None))


def client_ip(request: Request) -> str | None:
    """Best-effort client IP. Behind a reverse proxy, X-Forwarded-For's first
    hop is the real client."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else None


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User:
    """Resolve the authenticated user from the Bearer access token."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Nicht angemeldet.")
    token = authorization.split(" ", 1)[1]
    try:
        payload = decode_access_token(token)
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=401, detail="Ungültige Sitzung.") from exc
    user = await db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.status != "active":
        raise HTTPException(status_code=401, detail="Konto nicht aktiv.")
    return user


async def get_current_group_id(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    x_group_id: str | None = Header(default=None),
) -> uuid.UUID:
    """The household the request operates on — the single tenancy seam.

    Resolves the ``X-Group-Id`` header if the user is a member, otherwise their
    earliest membership. Every endpoint that touches group-owned data depends on
    this, so switching group is a header change and auth stays in one place.
    """
    requested = None
    if x_group_id:
        try:
            requested = uuid.UUID(x_group_id)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="Ungültige Gruppen-ID.") from exc
    group_id = await group_service.resolve_active_group(db, user, requested)
    if group_id is None:
        raise HTTPException(status_code=403, detail="Keine Gruppe zugeordnet.")
    return group_id


async def require_group_admin(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> uuid.UUID:
    """Guard for governance endpoints (invitations): the user must be admin of
    the active group."""
    membership = await group_service.get_membership(db, group_id, user.id)
    if membership is None or membership.role != "admin":
        raise HTTPException(status_code=403, detail="Nur Gruppen-Admins dürfen das.")
    return group_id


def get_arq(request: Request) -> object | None:
    """The ARQ pool if the worker backend is up, else None (upload falls back to
    FastAPI BackgroundTasks). Set in the app lifespan."""
    return getattr(request.app.state, "arq", None)
