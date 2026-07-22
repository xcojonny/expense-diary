import uuid
from typing import Any

from app.services.extraction_service import run_extraction


async def extract_receipt_task(ctx: dict[str, Any], receipt_id: str) -> None:
    """ARQ job: run the extraction pipeline for one receipt."""
    await run_extraction(uuid.UUID(receipt_id))
