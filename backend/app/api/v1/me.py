from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.db.session import get_db
from app.models import Group, GroupMember, User
from app.schemas.user import MembershipOut, MeOut

router = APIRouter(prefix="/me", tags=["me"])


@router.get("", response_model=MeOut)
async def me(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> MeOut:
    rows = (
        await db.execute(
            select(GroupMember.group_id, Group.name, GroupMember.role)
            .join(Group, Group.id == GroupMember.group_id)
            .where(GroupMember.user_id == user.id)
            .order_by(GroupMember.created_at)
        )
    ).all()
    return MeOut(
        id=user.id,
        email=user.email,
        display_name=user.display_name,
        is_instance_admin=user.is_instance_admin,
        memberships=[
            MembershipOut(group_id=gid, group_name=name, role=role) for gid, name, role in rows
        ],
    )
