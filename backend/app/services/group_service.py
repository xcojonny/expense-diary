from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models import Group


async def ensure_default_group(session: AsyncSession) -> Group:
    """Return the default household group, creating it if missing. Idempotent;
    called on startup and by the current-group dependency until real
    multi-group auth exists."""
    name = get_settings().default_group_name
    group = (
        await session.execute(select(Group).where(Group.name == name))
    ).scalar_one_or_none()
    if group is None:
        group = Group(name=name)
        session.add(group)
        await session.commit()
        await session.refresh(group)
    return group
