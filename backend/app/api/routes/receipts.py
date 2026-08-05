"""Bons: Upload, Liste, Detail, Bearbeitung, Beleg-Datei, Neu-Extraktion."""

from __future__ import annotations

from typing import Annotated

from fastapi import (
    APIRouter,
    File,
    HTTPException,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)

from app.api.deps import FileStoreDep, HouseholdDep, SessionDep, SettingsDep
from app.models import RECEIPT_STATUSES, Receipt, ReceiptStatus
from app.schemas import (
    LineItemCreate,
    LineItemOut,
    LineItemUpdate,
    ReceiptOut,
    ReceiptPage,
    ReceiptSummary,
    ReceiptUpdate,
)
from app.services import jobs as jobs_service
from app.services import receipts as receipts_service

router = APIRouter(tags=["receipts"])


def _summary(receipt: Receipt) -> ReceiptSummary:
    return ReceiptSummary(
        id=receipt.id,
        status=receipt.status,
        store_name=receipt.store_name,
        purchased_at=receipt.purchased_at,
        total_cents=receipt.total_cents,
        currency=receipt.currency,
        line_item_count=len(receipt.line_items),
        created_at=receipt.created_at,
    )


async def _load(session: SessionDep, receipt_id: int, household_id: int) -> Receipt:
    receipt = await receipts_service.get(session, receipt_id, household_id=household_id)
    if receipt is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Bon nicht gefunden.")
    return receipt


@router.get("/receipts", response_model=ReceiptPage)
async def list_receipts(
    session: SessionDep,
    household: HouseholdDep,
    status_filter: Annotated[str | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ReceiptPage:
    if status_filter is not None and status_filter not in RECEIPT_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unbekannter Status: {status_filter}"
        )
    receipts, total = await receipts_service.list_receipts(
        session, household_id=household.id, status=status_filter, limit=limit, offset=offset
    )
    return ReceiptPage(items=[_summary(r) for r in receipts], total=total)


@router.post("/receipts", response_model=ReceiptOut, status_code=status.HTTP_201_CREATED)
async def upload_receipt(
    request: Request,
    session: SessionDep,
    settings: SettingsDep,
    file_store: FileStoreDep,
    household: HouseholdDep,
    file: Annotated[UploadFile, File()],
) -> Receipt:
    """Beleg hochladen und die Extraktion einplanen.

    Der Typ kommt aus den Magic Bytes, nicht aus dem Content-Type des Clients.
    """
    data = await file.read()
    try:
        receipt = await receipts_service.create_from_upload(
            session,
            household_id=household.id,
            data=data,
            file_store=file_store,
            max_bytes=settings.upload_max_bytes,
            # Ein Bearer-Token kommt vom iOS-Kurzbefehl, ein Cookie aus dem Browser.
            source="shortcut" if request.headers.get("Authorization") else "upload",
            currency=settings.currency,
        )
    except receipts_service.UploadError as exc:
        # 422 als Zahl: der Starlette-Konstantenname wandert zwischen Versionen.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await session.commit()
    # Erst nach dem Commit wecken — sonst sieht der Worker den Job noch nicht.
    jobs_service.wake_worker()
    # Neu laden, damit `line_items` für die Antwort geladen ist: die Collection
    # eines gerade geflushten Objekts gilt als ungeladen, und das Serialisieren
    # würde sonst mitten in der Antwort eine Lazy-Load-Abfrage auslösen.
    return await _load(session, receipt.id, household.id)


@router.get("/receipts/{receipt_id}", response_model=ReceiptOut)
async def get_receipt(session: SessionDep, household: HouseholdDep, receipt_id: int) -> Receipt:
    return await _load(session, receipt_id, household.id)


@router.get("/receipts/{receipt_id}/file")
async def get_receipt_file(
    session: SessionDep, file_store: FileStoreDep, household: HouseholdDep, receipt_id: int
) -> Response:
    """Originalbeleg ausliefern — authentifiziert, damit die Datei nicht über
    einen offenen `/media`-Mount erreichbar ist."""
    receipt = await _load(session, receipt_id, household.id)
    if not receipt.file_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Kein Beleg vorhanden.")
    try:
        data = await file_store.read(receipt.file_path)
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Beleg-Datei fehlt."
        ) from exc
    return Response(
        content=data,
        media_type=receipt.file_media_type or "application/octet-stream",
        headers={"Cache-Control": "private, max-age=3600"},
    )


@router.patch("/receipts/{receipt_id}", response_model=ReceiptOut)
async def update_receipt(
    session: SessionDep, household: HouseholdDep, receipt_id: int, payload: ReceiptUpdate
) -> Receipt:
    receipt = await _load(session, receipt_id, household.id)
    await receipts_service.update_header(
        session,
        receipt,
        store_name=payload.store_name,
        purchased_at=payload.purchased_at,
        total_cents=payload.total_cents,
    )
    return await _load(session, receipt_id, household.id)


@router.post("/receipts/{receipt_id}/reviewed", response_model=ReceiptOut)
async def mark_reviewed(session: SessionDep, household: HouseholdDep, receipt_id: int) -> Receipt:
    """`needs_review → done`, nachdem ein Mensch draufgeschaut hat."""
    receipt = await _load(session, receipt_id, household.id)
    if receipt.status != ReceiptStatus.NEEDS_REVIEW.value:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nur ein Bon im Status „Prüfen“ kann bestätigt werden.",
        )
    await receipts_service.mark_reviewed(session, receipt)
    return await _load(session, receipt_id, household.id)


@router.post("/receipts/{receipt_id}/reprocess", response_model=ReceiptOut)
async def reprocess(session: SessionDep, household: HouseholdDep, receipt_id: int) -> Receipt:
    receipt = await _load(session, receipt_id, household.id)
    if not receipt.file_path:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ohne Beleg-Datei ist keine Neu-Extraktion möglich.",
        )
    await receipts_service.requeue(session, receipt)
    await session.commit()
    jobs_service.wake_worker()
    return await _load(session, receipt_id, household.id)


@router.delete("/receipts/{receipt_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_receipt(
    session: SessionDep, file_store: FileStoreDep, household: HouseholdDep, receipt_id: int
) -> None:
    receipt = await _load(session, receipt_id, household.id)
    await receipts_service.delete_receipt(session, receipt, file_store=file_store)


# --- Positionen ---------------------------------------------------------------


@router.post(
    "/receipts/{receipt_id}/line-items",
    response_model=LineItemOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_line_item(
    session: SessionDep, household: HouseholdDep, receipt_id: int, payload: LineItemCreate
) -> object:
    receipt = await _load(session, receipt_id, household.id)
    return await receipts_service.add_line_item(
        session,
        receipt,
        name=payload.name,
        total_price_cents=payload.total_price_cents,
        quantity_milli=payload.quantity_milli,
        unit=payload.unit,
        unit_price_cents=payload.unit_price_cents,
        category_id=payload.category_id,
        kind=payload.kind,
        vat_class=payload.vat_class,
    )


@router.patch("/line-items/{line_item_id}", response_model=LineItemOut)
async def update_line_item(
    session: SessionDep, household: HouseholdDep, line_item_id: int, payload: LineItemUpdate
) -> object:
    line_item = await receipts_service.get_line_item(
        session, line_item_id, household_id=household.id
    )
    if line_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Position nicht gefunden."
        )
    return await receipts_service.update_line_item(
        session,
        line_item,
        household_id=household.id,
        name=payload.name,
        total_price_cents=payload.total_price_cents,
        quantity_milli=payload.quantity_milli,
        unit=payload.unit,
        unit_price_cents=payload.unit_price_cents,
        category_id=payload.category_id,
        clear_category=payload.clear_category,
        kind=payload.kind,
    )


@router.delete("/line-items/{line_item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_line_item(
    session: SessionDep, household: HouseholdDep, line_item_id: int
) -> None:
    line_item = await receipts_service.get_line_item(
        session, line_item_id, household_id=household.id
    )
    if line_item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Position nicht gefunden."
        )
    await receipts_service.delete_line_item(session, line_item)
