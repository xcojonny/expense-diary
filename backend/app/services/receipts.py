"""Bons: Upload, Bearbeitung, Löschung.

Grundsatz bei der Bearbeitung: `normalized_name` und `item_id` setzt immer der
Server über `services/items.py` (nie der Client), damit eine korrigierte
Position am selben Trend-Anker landet wie eine extrahierte.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.domain.money import unit_price_from_total
from app.integrations.files import SUPPORTED_MEDIA_TYPES, FileStore, detect_media_type
from app.models import LineItem, Receipt, ReceiptStatus
from app.services import items as items_service
from app.services import jobs as jobs_service

log = get_logger(__name__)


class UploadError(ValueError):
    """Die hochgeladene Datei ist zu groß oder kein unterstützter Typ."""


async def create_from_upload(
    session: AsyncSession,
    *,
    household_id: int,
    data: bytes,
    file_store: FileStore,
    max_bytes: int,
    source: str = "upload",
    currency: str = "EUR",
) -> Receipt:
    """Datei prüfen, ablegen, Bon anlegen und Extraktion einplanen."""
    if not data:
        raise UploadError("Die Datei ist leer.")
    if len(data) > max_bytes:
        raise UploadError(
            f"Die Datei ist größer als {max_bytes // (1024 * 1024)} MB."
        )

    # Magic Bytes, nicht der Content-Type des Clients.
    media_type = detect_media_type(data)
    if media_type is None or media_type not in SUPPORTED_MEDIA_TYPES:
        raise UploadError("Nur JPEG, PNG, WebP, HEIC oder PDF werden unterstützt.")

    relative_path = await file_store.save(data, media_type)
    receipt = Receipt(
        household_id=household_id,
        status=ReceiptStatus.UPLOADED.value,
        file_path=relative_path,
        file_media_type=media_type,
        source=source,
        currency=currency,
    )
    session.add(receipt)
    await session.flush()

    await jobs_service.enqueue(session, receipt.id)
    log.info(
        "receipt.uploaded",
        extra={
            "receipt_id": receipt.id,
            "household_id": household_id,
            "media_type": media_type,
            "bytes": len(data),
        },
    )
    return receipt


async def get(session: AsyncSession, receipt_id: int, *, household_id: int) -> Receipt | None:
    """Bon laden — nur innerhalb des Haushalts. Ein fremder Bon ist „nicht
    gefunden", nicht „verboten": so verrät die API nicht, welche IDs existieren."""
    return (
        await session.execute(
            sa.select(Receipt).where(
                Receipt.id == receipt_id, Receipt.household_id == household_id
            )
        )
    ).scalar_one_or_none()


async def list_receipts(
    session: AsyncSession,
    *,
    household_id: int,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Receipt], int]:
    """`(bons, gesamtzahl)` — neueste zuerst, nach wirksamem Kaufdatum."""
    conditions: list[sa.ColumnElement[bool]] = [Receipt.household_id == household_id]
    if status:
        conditions.append(Receipt.status == status)
    effective = sa.func.coalesce(Receipt.purchased_at, Receipt.created_at)

    total = (
        await session.execute(sa.select(sa.func.count(Receipt.id)).where(*conditions))
    ).scalar_one()
    rows = (
        (
            await session.execute(
                sa.select(Receipt)
                .where(*conditions)
                .order_by(effective.desc(), Receipt.id.desc())
                .limit(limit)
                .offset(offset)
            )
        )
        .scalars()
        .all()
    )
    return list(rows), total


async def update_header(
    session: AsyncSession,
    receipt: Receipt,
    *,
    store_name: str | None = None,
    purchased_at: datetime | None = None,
    total_cents: int | None = None,
    status: str | None = None,
) -> Receipt:
    if store_name is not None:
        receipt.store_name = store_name.strip() or None
    if purchased_at is not None:
        receipt.purchased_at = purchased_at
    if total_cents is not None:
        receipt.total_cents = total_cents
    if status is not None:
        receipt.status = status
    await session.flush()
    return receipt


async def mark_reviewed(session: AsyncSession, receipt: Receipt) -> Receipt:
    """`needs_review → done`. Der Fehlerhinweis verschwindet dabei."""
    receipt.status = ReceiptStatus.DONE.value
    receipt.error = None
    await session.flush()
    return receipt


async def add_line_item(
    session: AsyncSession,
    receipt: Receipt,
    *,
    name: str,
    total_price_cents: int,
    quantity_milli: int | None = None,
    unit: str | None = None,
    unit_price_cents: int | None = None,
    category_id: int | None = None,
    kind: str = "product",
    vat_class: str | None = None,
) -> LineItem:
    next_position = (
        await session.execute(
            sa.select(sa.func.coalesce(sa.func.max(LineItem.position), -1) + 1).where(
                LineItem.receipt_id == receipt.id
            )
        )
    ).scalar_one()

    line_item = LineItem(
        receipt_id=receipt.id,
        position=next_position,
        name=name.strip(),
        total_price_cents=total_price_cents,
        quantity_milli=quantity_milli,
        unit=unit,
        unit_price_cents=unit_price_cents
        or unit_price_from_total(total_price_cents, quantity_milli),
        category_id=category_id,
        kind=kind,
        vat_class=vat_class,
    )
    session.add(line_item)
    await session.flush()
    await items_service.apply_product_mapping(
        session, line_item, household_id=receipt.household_id
    )
    await session.flush()
    return line_item


async def get_line_item(
    session: AsyncSession, line_item_id: int, *, household_id: int
) -> LineItem | None:
    """Position laden — über den Bon auf den Haushalt geprüft. Ohne diesen Join
    wäre `/line-items/{id}` ein Loch in der Mandantentrennung."""
    return (
        await session.execute(
            sa.select(LineItem)
            .join(Receipt, LineItem.receipt_id == Receipt.id)
            .where(LineItem.id == line_item_id, Receipt.household_id == household_id)
        )
    ).scalar_one_or_none()


async def update_line_item(
    session: AsyncSession,
    line_item: LineItem,
    *,
    household_id: int,
    name: str | None = None,
    total_price_cents: int | None = None,
    quantity_milli: int | None = None,
    unit: str | None = None,
    unit_price_cents: int | None = None,
    category_id: int | None = None,
    clear_category: bool = False,
    kind: str | None = None,
) -> LineItem:
    remap = False

    if name is not None and name.strip() != line_item.name:
        line_item.name = name.strip()
        remap = True
    if kind is not None and kind != line_item.kind:
        line_item.kind = kind
        remap = True
    if total_price_cents is not None:
        line_item.total_price_cents = total_price_cents
    if quantity_milli is not None:
        line_item.quantity_milli = quantity_milli
    if unit is not None:
        line_item.unit = unit.strip() or None
    if clear_category:
        line_item.category_id = None
    elif category_id is not None:
        line_item.category_id = category_id

    if unit_price_cents is not None:
        line_item.unit_price_cents = unit_price_cents
    elif total_price_cents is not None or quantity_milli is not None:
        # Preis oder Menge geändert → Stückpreis neu ableiten, sonst steht dort
        # ein Wert, der nicht mehr zu den anderen beiden passt.
        line_item.unit_price_cents = unit_price_from_total(
            line_item.total_price_cents, line_item.quantity_milli
        )

    if remap:
        await items_service.apply_product_mapping(
            session, line_item, household_id=household_id
        )

    await session.flush()
    return line_item


async def delete_line_item(session: AsyncSession, line_item: LineItem) -> None:
    await session.delete(line_item)
    await session.flush()


async def delete_receipt(
    session: AsyncSession, receipt: Receipt, *, file_store: FileStore
) -> None:
    """Bon samt Positionen (FK-Kaskade) und Beleg-Datei entfernen."""
    path = receipt.file_path
    await session.delete(receipt)
    await session.flush()
    if path:
        await file_store.delete(path)


async def requeue(session: AsyncSession, receipt: Receipt) -> None:
    """Neu-Extraktion einplanen."""
    receipt.status = ReceiptStatus.UPLOADED.value
    receipt.error = None
    await jobs_service.enqueue(session, receipt.id)
    await session.flush()
