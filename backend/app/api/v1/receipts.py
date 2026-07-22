import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_arq, get_current_group_id
from app.core.config import get_settings
from app.db.session import get_db
from app.domain.upload import detect_media_type
from app.models import Receipt
from app.schemas.receipt import ReceiptDetailOut, ReceiptOut
from app.services import upload_service
from app.services.extraction_service import run_extraction

router = APIRouter(prefix="/receipts", tags=["receipts"])


async def _schedule_extraction(
    request: Request, background_tasks: BackgroundTasks, receipt_id: uuid.UUID
) -> None:
    """Prefer the ARQ worker; fall back to an in-process BackgroundTask when no
    Redis/worker is available (both are sanctioned by the brief)."""
    arq = get_arq(request)
    if arq is not None:
        await arq.enqueue_job("extract_receipt_task", str(receipt_id))  # type: ignore[attr-defined]
    else:
        background_tasks.add_task(run_extraction, receipt_id)


@router.post("", response_model=ReceiptOut, status_code=201)
async def upload_receipt(
    request: Request,
    background_tasks: BackgroundTasks,
    file: UploadFile,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> Receipt:
    settings = get_settings()
    data = await file.read()
    if not data:
        raise HTTPException(status_code=400, detail="Leere Datei.")
    if len(data) > settings.upload_max_bytes:
        raise HTTPException(status_code=413, detail="Datei ist zu groß.")

    media_type = detect_media_type(data)
    if media_type is None or media_type not in settings.upload_allowed_types:
        raise HTTPException(
            status_code=415, detail="Nicht unterstütztes Dateiformat (nur JPEG, PNG, WebP, PDF)."
        )

    receipt = await upload_service.create_receipt(
        db, group_id=group_id, data=data, media_type=media_type
    )
    await _schedule_extraction(request, background_tasks, receipt.id)
    return receipt


@router.get("", response_model=list[ReceiptOut])
async def list_receipts(
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> list[Receipt]:
    result = await db.execute(
        select(Receipt).where(Receipt.group_id == group_id).order_by(Receipt.created_at.desc())
    )
    return list(result.scalars().all())


@router.get("/{receipt_id}", response_model=ReceiptDetailOut)
async def get_receipt(
    receipt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> Receipt:
    """Receipt detail incl. line items — this is what the frontend polls (~2 s)
    until the status leaves ``processing``."""
    result = await db.execute(
        select(Receipt)
        .where(Receipt.id == receipt_id, Receipt.group_id == group_id)
        .options(selectinload(Receipt.line_items))
    )
    receipt = result.scalar_one_or_none()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Bon nicht gefunden.")
    return receipt
