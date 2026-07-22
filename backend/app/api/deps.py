import uuid

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services import group_service


async def get_current_group_id(db: AsyncSession = Depends(get_db)) -> uuid.UUID:
    """The household whose data the request operates on.

    This is the single seam for tenancy: today it resolves the bootstrapped
    default group; once auth lands it derives the group from the authenticated
    user's active membership — endpoints keep depending on this unchanged.
    """
    group = await group_service.ensure_default_group(db)
    return group.id


def get_arq(request: Request) -> object | None:
    """The ARQ pool if the worker backend is up, else None (the upload path
    falls back to FastAPI BackgroundTasks). Set in the app lifespan."""
    return getattr(request.app.state, "arq", None)
