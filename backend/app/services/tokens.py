"""API-Tokens für headless-Clients (iOS-Kurzbefehl).

Gespeichert wird nur der SHA-256-Hash; der Klartext ist genau einmal — bei der
Erstellung — sichtbar.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_token, hash_api_token
from app.db.base import utcnow
from app.models import ApiToken


async def list_tokens(session: AsyncSession) -> list[ApiToken]:
    return list(
        (await session.execute(sa.select(ApiToken).order_by(ApiToken.created_at.desc())))
        .scalars()
        .all()
    )


async def create_token(session: AsyncSession, *, name: str) -> tuple[ApiToken, str]:
    """`(datensatz, klartext)` — der Klartext ist danach nicht wiederherstellbar."""
    plain, digest = generate_api_token()
    token = ApiToken(name=name.strip() or "Unbenannt", token_hash=digest)
    session.add(token)
    await session.flush()
    return token, plain


async def resolve(session: AsyncSession, plain: str) -> ApiToken | None:
    """Token einlösen und `last_used_at` fortschreiben."""
    token = (
        await session.execute(
            sa.select(ApiToken).where(ApiToken.token_hash == hash_api_token(plain))
        )
    ).scalar_one_or_none()
    if token is not None:
        token.last_used_at = utcnow()
    return token


async def revoke(session: AsyncSession, token: ApiToken) -> None:
    await session.delete(token)
    await session.flush()


async def get(session: AsyncSession, token_id: int) -> ApiToken | None:
    return await session.get(ApiToken, token_id)
