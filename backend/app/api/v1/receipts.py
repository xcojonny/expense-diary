import uuid

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    UploadFile,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_arq, get_current_group_id
from app.core.config import get_settings
from app.db.session import get_db
from app.domain.upload import detect_media_type
from app.integrations.storage.local import get_storage
from app.models import LineItem, Receipt, ReceiptStatus
from app.schemas.receipt import (
    LineItemOut,
    LineItemWrite,
    ReceiptDetailOut,
    ReceiptOut,
    ReceiptUpdate,
)
from app.services import receipt_edit_service, upload_service
from app.services.extraction_service import run_extraction
from app.services.receipt_edit_service import UnknownCategory

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


@router.get("/{receipt_id}/file")
async def get_receipt_file(
    receipt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> Response:
    """Stream the original uploaded receipt (image or PDF) so the user can view
    it against the extracted data. Group-scoped — unlike the raw ``/media`` mount
    this enforces the same tenancy seam as every other receipt route."""
    receipt = await _get_owned_receipt(db, receipt_id, group_id)
    try:
        data = get_storage().read(receipt.image_path)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Beleg-Datei nicht gefunden.") from exc
    media_type = detect_media_type(data) or "application/octet-stream"
    return Response(
        content=data,
        media_type=media_type,
        headers={
            # inline so the browser renders it in a tab/frame instead of forcing
            # a download; the stored file content never changes for a receipt.
            "Content-Disposition": f'inline; filename="{receipt.image_path}"',
            "Cache-Control": "private, max-age=3600",
        },
    )


async def _get_owned_receipt(
    db: AsyncSession, receipt_id: uuid.UUID, group_id: uuid.UUID
) -> Receipt:
    receipt = (
        await db.execute(
            select(Receipt).where(Receipt.id == receipt_id, Receipt.group_id == group_id)
        )
    ).scalar_one_or_none()
    if receipt is None:
        raise HTTPException(status_code=404, detail="Bon nicht gefunden.")
    return receipt


async def _get_owned_line(
    db: AsyncSession, receipt: Receipt, line_id: uuid.UUID
) -> LineItem:
    line = (
        await db.execute(
            select(LineItem).where(LineItem.id == line_id, LineItem.receipt_id == receipt.id)
        )
    ).scalar_one_or_none()
    if line is None:
        raise HTTPException(status_code=404, detail="Position nicht gefunden.")
    return line


@router.patch("/{receipt_id}", response_model=ReceiptOut)
async def update_receipt(
    receipt_id: uuid.UUID,
    data: ReceiptUpdate,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> Receipt:
    receipt = await _get_owned_receipt(db, receipt_id, group_id)
    return await receipt_edit_service.update_receipt(db, receipt, data)


@router.post("/{receipt_id}/reprocess", response_model=ReceiptOut)
async def reprocess_receipt(
    receipt_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> Receipt:
    """Re-run extraction on the already-stored file — e.g. after parser/category
    improvements. Idempotent: extraction replaces the receipt's line items, so
    this recomputes items, categories and status from scratch."""
    receipt = await _get_owned_receipt(db, receipt_id, group_id)
    receipt.status = ReceiptStatus.uploaded
    receipt.error = None
    await db.commit()
    await _schedule_extraction(request, background_tasks, receipt.id)
    await db.refresh(receipt)
    return receipt


@router.delete("/{receipt_id}", status_code=204)
async def delete_receipt(
    receipt_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> None:
    receipt = await _get_owned_receipt(db, receipt_id, group_id)
    await receipt_edit_service.delete_receipt(db, receipt)


@router.post("/{receipt_id}/line-items", response_model=LineItemOut, status_code=201)
async def add_line_item(
    receipt_id: uuid.UUID,
    data: LineItemWrite,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> LineItem:
    receipt = await _get_owned_receipt(db, receipt_id, group_id)
    try:
        return await receipt_edit_service.add_line_item(db, receipt, data)
    except UnknownCategory as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{receipt_id}/line-items/{line_id}", response_model=LineItemOut)
async def update_line_item(
    receipt_id: uuid.UUID,
    line_id: uuid.UUID,
    data: LineItemWrite,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> LineItem:
    receipt = await _get_owned_receipt(db, receipt_id, group_id)
    line = await _get_owned_line(db, receipt, line_id)
    try:
        return await receipt_edit_service.update_line_item(db, receipt, line, data)
    except UnknownCategory as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{receipt_id}/line-items/{line_id}", status_code=204)
async def delete_line_item(
    receipt_id: uuid.UUID,
    line_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> None:
    receipt = await _get_owned_receipt(db, receipt_id, group_id)
    line = await _get_owned_line(db, receipt, line_id)
    await receipt_edit_service.delete_line_item(db, line)
