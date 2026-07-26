"""Group (household) membership + invitation use-cases."""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import generate_token, hash_token
from app.integrations.mail.sender import Email, send_mail
from app.models import Group, GroupInvitation, GroupMember, User
from app.services import auth_service


async def create_group(session: AsyncSession, *, user: User, name: str) -> Group:
    group = Group(name=name.strip() or "Haushalt", created_by=user.id)
    session.add(group)
    await session.flush()
    session.add(GroupMember(group_id=group.id, user_id=user.id, role="admin"))
    await session.commit()
    await session.refresh(group)
    return group


async def list_memberships(session: AsyncSession, user_id: uuid.UUID) -> list[GroupMember]:
    return list(
        (
            await session.execute(
                select(GroupMember)
                .where(GroupMember.user_id == user_id)
                .order_by(GroupMember.created_at)
            )
        )
        .scalars()
        .all()
    )


async def get_membership(
    session: AsyncSession, group_id: uuid.UUID, user_id: uuid.UUID
) -> GroupMember | None:
    return (
        await session.execute(
            select(GroupMember).where(
                GroupMember.group_id == group_id, GroupMember.user_id == user_id
            )
        )
    ).scalar_one_or_none()


async def resolve_active_group(
    session: AsyncSession, user: User, requested: uuid.UUID | None
) -> uuid.UUID | None:
    """The group a request operates on: the requested one if the user is a
    member, else their earliest membership. None only if they belong to none."""
    memberships = await list_memberships(session, user.id)
    if requested is not None:
        for m in memberships:
            if m.group_id == requested:
                return requested
    return memberships[0].group_id if memberships else None


async def invite(
    session: AsyncSession, *, group: Group, inviter: User, email: str, role: str
) -> None:
    """Create + email a group invitation. Callers return 202 regardless."""
    settings = get_settings()
    raw = generate_token()
    session.add(
        GroupInvitation(
            group_id=group.id,
            email=email,
            role=role if role in ("admin", "member") else "member",
            token_hash=hash_token(raw),
            invited_by=inviter.id,
            expires_at=datetime.now(UTC) + timedelta(days=settings.invitation_ttl_days),
        )
    )
    await session.commit()
    link = f"{settings.base_url}/login?invite={raw}"
    await send_mail(
        Email(
            to=email,
            subject=f"Einladung zum Haushalt „{group.name}“",
            text=f"Hallo,\n\n{inviter.display_name} lädt dich in den Haushalt "
            f"„{group.name}“ ein:\n{link}\n\n"
            f"Die Einladung ist {settings.invitation_ttl_days} Tage gültig.",
        )
    )


async def accept_invitation(session: AsyncSession, raw: str) -> User | None:
    """Validate an invitation token, create/activate the invited user and their
    membership, and return the user so the caller can issue a session."""
    inv = (
        await session.execute(
            select(GroupInvitation).where(GroupInvitation.token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()
    now = datetime.now(UTC)
    if inv is None or inv.accepted_at is not None or inv.expires_at < now:
        return None

    user = await auth_service.get_user_by_email(session, inv.email)
    if user is None:
        user = await auth_service.create_user(
            session, email=inv.email, display_name=inv.email.split("@")[0], status="active"
        )
    elif user.status == "pending":
        user.status = "active"

    if await get_membership(session, inv.group_id, user.id) is None:
        session.add(GroupMember(group_id=inv.group_id, user_id=user.id, role=inv.role))
    inv.accepted_at = now
    user.last_login_at = now
    await session.commit()
    return user
