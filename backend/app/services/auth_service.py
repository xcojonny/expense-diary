"""Authentication use-cases: initial-admin bootstrap, magic-link login, session
issuance/rotation, and OIDC user provisioning.

Simplifications vs. a public SaaS (documented on purpose): magic links are
single-use + short-lived but not browser-bound (no pairing codes); refresh
tokens rotate and are revocable but there is no family reuse-detection. Both are
proportionate for a private homelab and can harden later.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import create_access_token, generate_token, hash_token
from app.integrations.mail.sender import Email, send_mail
from app.models import Group, GroupMember, MagicLinkToken, OidcIdentity, RefreshToken, User


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


# -- Magic link ---------------------------------------------------------------


async def request_magic_link(session: AsyncSession, email: str) -> None:
    """Create + email a login link for an active user. Silent no-op otherwise
    (no account enumeration). Callers always return 202."""
    user = await get_user_by_email(session, email)
    if user is None or user.status != "active":
        return
    settings = get_settings()
    raw = generate_token()
    session.add(
        MagicLinkToken(
            email=email,
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(minutes=settings.magic_link_ttl_minutes),
        )
    )
    await session.commit()
    link = f"{settings.base_url}/login?token={raw}"
    await send_mail(
        Email(
            to=email,
            subject="Dein Anmeldelink fürs Haushaltsbuch",
            text=f"Hallo,\n\nmit diesem Link meldest du dich an:\n{link}\n\n"
            f"Der Link ist {settings.magic_link_ttl_minutes} Minuten gültig.",
        )
    )


async def verify_magic_link(session: AsyncSession, raw: str) -> User | None:
    token = (
        await session.execute(
            select(MagicLinkToken).where(MagicLinkToken.token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()
    if token is None or token.used_at is not None:
        return None
    if token.expires_at < datetime.now(UTC):
        return None
    if token.user_id is None:
        return None
    user = await session.get(User, token.user_id)
    if user is None or user.status != "active":
        return None
    token.used_at = datetime.now(UTC)
    user.last_login_at = datetime.now(UTC)
    await session.commit()
    return user


# -- Sessions -----------------------------------------------------------------


async def issue_session(session: AsyncSession, user: User) -> tuple[str, str]:
    """Return (access_token JWT, raw refresh token). The refresh token's hash is
    stored; the raw value goes into an httpOnly cookie by the caller."""
    settings = get_settings()
    raw = generate_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=datetime.now(UTC) + timedelta(days=settings.refresh_token_ttl_days),
        )
    )
    await session.commit()
    access = create_access_token(user.id, is_instance_admin=user.is_instance_admin)
    return access, raw


async def rotate_refresh(session: AsyncSession, raw: str) -> tuple[str, str] | None:
    """Validate + rotate a refresh token. Returns (access, new_raw) or None."""
    token = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if token is None or token.revoked_at is not None or token.expires_at < now:
        return None
    user = await session.get(User, token.user_id)
    if user is None or user.status != "active":
        return None
    token.revoked_at = now
    token.last_used_at = now
    new_raw = generate_token()
    session.add(
        RefreshToken(
            user_id=user.id,
            token_hash=hash_token(new_raw),
            expires_at=now + timedelta(days=get_settings().refresh_token_ttl_days),
        )
    )
    await session.commit()
    return create_access_token(user.id, is_instance_admin=user.is_instance_admin), new_raw


async def revoke_refresh(session: AsyncSession, raw: str) -> None:
    token = (
        await session.execute(
            select(RefreshToken).where(RefreshToken.token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()
    if token is not None and token.revoked_at is None:
        token.revoked_at = datetime.now(UTC)
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
            user.last_login_at = datetime.now(UTC)
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
    session.add(OidcIdentity(user_id=user.id, issuer=issuer, subject=subject))
    user.last_login_at = datetime.now(UTC)
    await ensure_personal_group(session, user)
    await session.commit()
    return user
