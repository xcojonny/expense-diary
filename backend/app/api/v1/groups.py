import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, require_group_admin
from app.db.session import get_db
from app.models import Group, GroupMember, User
from app.schemas.group import GroupCreate, GroupOut, InvitationCreate
from app.services import group_service

router = APIRouter(prefix="/groups", tags=["groups"])


@router.get("", response_model=list[GroupOut])
async def list_groups(
    db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)
) -> list[GroupOut]:
    rows = (
        await db.execute(
            select(Group.id, Group.name, GroupMember.role)
            .join(GroupMember, GroupMember.group_id == Group.id)
            .where(GroupMember.user_id == user.id)
            .order_by(GroupMember.created_at)
        )
    ).all()
    return [GroupOut(id=gid, name=name, role=role) for gid, name, role in rows]


@router.post("", response_model=GroupOut, status_code=201)
async def create_group(
    data: GroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> GroupOut:
    group = await group_service.create_group(db, user=user, name=data.name)
    return GroupOut(id=group.id, name=group.name, role="admin")


@router.post("/invitations", status_code=202)
async def invite(
    data: InvitationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
    group_id: uuid.UUID = Depends(require_group_admin),
) -> dict[str, str]:
    group = await db.get(Group, group_id)
    assert group is not None  # guaranteed by require_group_admin
    await group_service.invite(db, group=group, inviter=user, email=str(data.email), role=data.role)
    return {"status": "accepted"}
