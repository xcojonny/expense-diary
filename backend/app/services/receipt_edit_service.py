"""Manual correction of receipts and their line items (phase 3).

Keeps the Item mapping consistent with extraction: any name/type change re-runs
``apply_product_mapping`` so a corrected line points at the right trend anchor.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.storage.local import get_storage
from app.models import Category, LineItem, Receipt
from app.schemas.receipt import LineItemWrite, ReceiptUpdate
from app.services.items import apply_product_mapping


class UnknownCategory(ValueError):
    """The referenced category does not exist."""


async def _check_category(session: AsyncSession, category_id: uuid.UUID | None) -> None:
    if category_id is None:
        return
    exists = (
        await session.execute(select(Category.id).where(Category.id == category_id))
    ).scalar_one_or_none()
    if exists is None:
        raise UnknownCategory("Kategorie nicht gefunden.")


async def update_receipt(
    session: AsyncSession, receipt: Receipt, data: ReceiptUpdate
) -> Receipt:
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(receipt, field, value)
    await session.commit()
    await session.refresh(receipt)
    return receipt


async def add_line_item(
    session: AsyncSession, receipt: Receipt, data: LineItemWrite
) -> LineItem:
    await _check_category(session, data.category_id)
    line = LineItem(receipt_id=receipt.id, **_editable(data))
    await apply_product_mapping(
        session, line, group_id=receipt.group_id, category_id=data.category_id
    )
    session.add(line)
    await session.commit()
    await session.refresh(line)
    return line


async def update_line_item(
    session: AsyncSession, receipt: Receipt, line: LineItem, data: LineItemWrite
) -> LineItem:
    await _check_category(session, data.category_id)
    for field, value in _editable(data).items():
        setattr(line, field, value)
    await apply_product_mapping(
        session, line, group_id=receipt.group_id, category_id=data.category_id
    )
    await session.commit()
    await session.refresh(line)
    return line


async def delete_line_item(session: AsyncSession, line: LineItem) -> None:
    await session.delete(line)
    await session.commit()


async def delete_receipt(session: AsyncSession, receipt: Receipt) -> None:
    get_storage().delete(receipt.image_path)  # best-effort; missing file is fine
    await session.delete(receipt)  # line items cascade
    await session.commit()


def _editable(data: LineItemWrite) -> dict[str, object]:
    # category_id is applied via apply_product_mapping/setattr; name/type drive
    # the mapping, so hand them through as plain columns here.
    return {
        "name": data.name,
        "quantity": data.quantity,
        "unit": data.unit,
        "unit_price": data.unit_price,
        "total_price": data.total_price,
        "vat_class": data.vat_class,
        "line_type": data.line_type,
        "category_id": data.category_id,
    }
