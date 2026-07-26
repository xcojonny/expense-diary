"""Authentication use-cases: initial-admin bootstrap, session issuance with
rotating refresh tokens (family reuse-detection), and OIDC provisioning.

Magic-link logic lives in ``magic_link_service``. Simplification vs. a public
SaaS, on purpose for a homelab: OIDC id_tokens aren't signature-verified (we call
userinfo over TLS instead).
"""

import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.security import create_access_token, generate_token, hash_token
from app.models import Group, GroupMember, OidcIdentity, RefreshToken, User

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(select(User).where(User.email == email))
    ).scalar_one_or_none()


async def create_user(
    session: AsyncSession,
    *,
    email: str,
    display_name: str,
    status: str = "active",
    is_instance_admin: bool = False,
) -> User:
    user = User(
        email=email,
        display_name=display_name or email.split("@")[0],
        status=status,
        is_instance_admin=is_instance_admin,
    )
    session.add(user)
    await session.flush()
    return user


async def _has_membership(session: AsyncSession, user_id: uuid.UUID) -> bool:
    return (
        await session.execute(select(GroupMember.id).where(GroupMember.user_id == user_id))
    ).first() is not None


async def ensure_personal_group(session: AsyncSession, user: User) -> None:
    """Give a user their own household if they belong to none, so a freshly
    provisioned account (OIDC/bootstrap) can start immediately."""
    if await _has_membership(session, user.id):
        return
    group = Group(name=f"Haushalt von {user.display_name}", created_by=user.id)
    session.add(group)
    await session.flush()
    session.add(GroupMember(group_id=group.id, user_id=user.id, role="admin"))


async def ensure_initial_admin(session: AsyncSession) -> None:
    """Bootstrap the configured admin as an active instance admin owning the
    default group. Idempotent; a no-op when INITIAL_ADMIN_EMAIL is unset."""
    settings = get_settings()
    if not settings.initial_admin_email:
        return
    email = str(settings.initial_admin_email)
    admin = await get_user_by_email(session, email)
    if admin is None:
        admin = await create_user(
            session, email=email, display_name="Admin", status="active", is_instance_admin=True
        )
    elif not admin.is_instance_admin:
        admin.is_instance_admin = True

    group = (
        await session.execute(select(Group).where(Group.name == settings.default_group_name))
    ).scalar_one_or_none()
    if group is None:
        group = Group(name=settings.default_group_name, created_by=admin.id)
        session.add(group)
        await session.flush()
    member = (
        await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group.id, GroupMember.user_id == admin.id
            )
        )
    ).scalar_one_or_none()
    if member is None:
        session.add(GroupMember(group_id=group.id, user_id=admin.id, role="admin"))
    await session.commit()


# -- Sessions (rotating refresh with reuse detection) -------------------------


async def issue_session(
    session: AsyncSession,
    user: User,
    *,
    user_agent: str | None = None,
    ip: str | None = None,
    family_id: uuid.UUID | None = None,
) -> tuple[str, str]:
    """Return (access_token JWT, raw refresh token). Only the refresh hash is
    stored; the raw value goes into an httpOnly cookie by the caller."""
    settings = get_settings()
    raw = generate_token()
    token = RefreshToken(
        user_id=user.id,
        token_hash=hash_token(raw),
        expires_at=_now() + timedelta(days=settings.refresh_token_ttl_days),
        user_agent=(user_agent or "")[:300] or None,
        ip=ip,
    )
    if family_id is not None:
        token.family_id = family_id
    session.add(token)
    user.last_login_at = _now()
    await session.commit()
    return create_access_token(user.id, is_instance_admin=user.is_instance_admin), raw


async def rotate_refresh_token(
    session: AsyncSession, raw: str, *, user_agent: str | None = None, ip: str | None = None
) -> tuple[str, str] | None:
    """Rotate a refresh token. Presenting an already-rotated (revoked) token is
    treated as theft and revokes the whole family — except a brief grace window
    for a parallel-tab rotation race while the family still has a live token.
    Returns (access, new_raw) or None."""
    settings = get_settings()
    token = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()
    if token is None:
        return None

    if token.revoked_at is not None:
        grace = timedelta(seconds=settings.refresh_reuse_grace_seconds)
        family_alive = await session.scalar(
            select(
                sa.exists().where(
                    RefreshToken.family_id == token.family_id,
                    RefreshToken.revoked_at.is_(None),
                )
            )
        )
        if not family_alive or token.revoked_at <= _now() - grace:
            await session.execute(
                sa.update(RefreshToken)
                .where(
                    RefreshToken.family_id == token.family_id,
                    RefreshToken.revoked_at.is_(None),
                )
                .values(revoked_at=_now())
            )
            await session.commit()
            log.warning("refresh reuse — family revoked", family_id=str(token.family_id))
            return None
        log.info("refresh reuse within grace", family_id=str(token.family_id), ip=ip)
    elif token.expires_at < _now():
        return None

    user = await session.get(User, token.user_id)
    if user is None or user.status != "active":
        return None

    token.revoked_at = token.revoked_at or _now()
    token.last_used_at = _now()
    return await issue_session(
        session, user, user_agent=user_agent, ip=ip, family_id=token.family_id
    )


async def revoke_refresh_token(session: AsyncSession, raw: str) -> None:
    """Logout: revoke the whole family of the presented token."""
    token = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()
    if token is not None:
        await session.execute(
            sa.update(RefreshToken)
            .where(RefreshToken.family_id == token.family_id, RefreshToken.revoked_at.is_(None))
            .values(revoked_at=_now())
        )
        await session.commit()


# -- OIDC (Authelia) ----------------------------------------------------------


async def upsert_oidc_user(
    session: AsyncSession, *, issuer: str, subject: str, email: str, display_name: str
) -> User:
    """Resolve the user behind an OIDC identity, provisioning on first login:
    match by (issuer, subject), else by email, else create; then link the
    identity and ensure the user has a household."""
    identity = (
        await session.execute(
            select(OidcIdentity).where(
                OidcIdentity.issuer == issuer, OidcIdentity.subject == subject
            )
        )
    ).scalar_one_or_none()
    if identity is not None:
        user = await session.get(User, identity.user_id)
        if user is not None:
            await ensure_personal_group(session, user)
            await session.commit()
            return user

    user = await get_user_by_email(session, email)
    if user is None:
        user = await create_user(
            session, email=email, display_name=display_name, status="active"
        )
    elif user.status == "pending":
        user.status = "active"
    user.email_verified_at = user.email_verified_at or _now()
    session.add(OidcIdentity(user_id=user.id, issuer=issuer, subject=subject))
    await ensure_personal_group(session, user)
    await session.commit()
    return user
