from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db.session import get_db

router = APIRouter(tags=["meta"])


@router.get("/healthz")
async def healthz() -> dict[str, str]:
    """Liveness — dependency-free so the container healthcheck stays cheap."""
    return {"status": "ok"}


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Readiness — verifies the database is reachable."""
    await db.execute(text("SELECT 1"))
    return {"status": "ready"}


@router.get("/version")
async def version() -> dict[str, Any]:
    settings = get_settings()
    return {"version": "0.1.0", "git_sha": settings.git_sha, "env": settings.app_env}
