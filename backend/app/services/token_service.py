"""Personal API tokens for headless clients (e.g. the iOS Shortcut that uploads
a receipt from the share sheet). Stored only as a SHA-256 hash; the raw value is
shown once on creation. Authentication resolves the token to its owning user;
group/tenancy is then resolved exactly like a browser session."""

import uuid
from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import generate_api_token, hash_token
from app.models import ApiToken, User


def _now() -> datetime:
    return datetime.now(UTC)


async def create_token(session: AsyncSession, user: User, *, name: str) -> tuple[ApiToken, str]:
    """Create a token for ``user`` and return (row, raw value). The raw value is
    the only time the secret exists in plaintext — the caller surfaces it once."""
    raw = generate_api_token()
    token = ApiToken(user_id=user.id, name=name.strip() or "Token", token_hash=hash_token(raw))
    session.add(token)
    await session.commit()
    await session.refresh(token)  # load server-side created_at for the response
    return token, raw


async def list_tokens(session: AsyncSession, user: User) -> list[ApiToken]:
    """The user's live (non-revoked) tokens, newest first — never the secret."""
    rows = await session.execute(
        select(ApiToken)
        .where(ApiToken.user_id == user.id, ApiToken.revoked_at.is_(None))
        .order_by(ApiToken.created_at.desc())
    )
    return list(rows.scalars().all())


async def revoke_token(session: AsyncSession, user: User, token_id: uuid.UUID) -> bool:
    """Revoke one of the user's tokens. Returns False if it doesn't exist / isn't
    theirs / is already revoked (so the caller can 404 without leaking)."""
    revoked = (
        await session.execute(
            sa.update(ApiToken)
            .where(
                ApiToken.id == token_id,
                ApiToken.user_id == user.id,
                ApiToken.revoked_at.is_(None),
            )
            .values(revoked_at=_now())
            .returning(ApiToken.id)
        )
    ).scalar_one_or_none()
    if revoked is not None:
        await session.commit()
    return revoked is not None


async def user_for_token(session: AsyncSession, raw: str) -> User | None:
    """Resolve the active user behind a raw API token, or None. Bumps
    ``last_used_at`` best-effort so a stale token is recognizable in the UI."""
    token = (
        await session.execute(
            select(ApiToken).where(
                ApiToken.token_hash == hash_token(raw), ApiToken.revoked_at.is_(None)
            )
        )
    ).scalar_one_or_none()
    if token is None:
        return None
    user = await session.get(User, token.user_id)
    if user is None or user.status != "active":
        return None
    await session.execute(
        sa.update(ApiToken).where(ApiToken.id == token.id).values(last_used_at=_now())
    )
    await session.commit()
    return user
