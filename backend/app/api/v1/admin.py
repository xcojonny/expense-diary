from typing import Any

from fastapi import APIRouter, Query

from app.core.logging import get_recent_logs
from app.schemas.admin import LogEntryOut

# Instance-admin-only. The mount applies `require_instance_admin` to the whole
# router, so every endpoint here is admin-gated.
router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/logs", response_model=list[LogEntryOut])
async def logs(
    limit: int = Query(200, ge=1, le=1000),
    level: str | None = Query(None, description="Minimum level, e.g. warning"),
) -> list[dict[str, Any]]:
    """Recent backend log events (in-memory ring, since the last restart)."""
    return get_recent_logs(limit=limit, min_level=level)
