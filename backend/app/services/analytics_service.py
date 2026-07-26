"""Analytics DB access: fetch flattened purchase records for a period. All the
computation happens in the pure ``domain/aggregation`` functions on top of what
this returns."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from app.domain.aggregation import PurchaseRecord
from app.models import Category, Item, LineItem, Receipt


def month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """[start, end) UTC bounds for a calendar month."""
    start = datetime(year, month, 1, tzinfo=UTC)
    end = (
        datetime(year + 1, 1, 1, tzinfo=UTC)
        if month == 12
        else datetime(year, month + 1, 1, tzinfo=UTC)
    )
    return start, end


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _base_query(group_id: uuid.UUID) -> tuple[Select[Any], ColumnElement[datetime]]:
    # Effective date = purchased_at, falling back to created_at when the receipt
    # date wasn't extracted.
    when = func.coalesce(Receipt.purchased_at, Receipt.created_at)
    return (
        select(
            LineItem.receipt_id,
            when.label("when"),
            Receipt.store_name,
            LineItem.line_type,
            LineItem.category_id,
            Category.name.label("category_name"),
            LineItem.item_id,
            func.coalesce(Item.display_name, LineItem.name).label("name"),
            LineItem.quantity,
            LineItem.unit,
            LineItem.unit_price,
            LineItem.total_price,
        )
        .join(Receipt, LineItem.receipt_id == Receipt.id)
        .outerjoin(Category, LineItem.category_id == Category.id)
        .outerjoin(Item, LineItem.item_id == Item.id)
        .where(Receipt.group_id == group_id)
    ), when


async def _rows_to_records(session: AsyncSession, stmt: Select[Any]) -> list[PurchaseRecord]:
    rows = (await session.execute(stmt)).all()
    return [
        PurchaseRecord(
            receipt_id=row.receipt_id,
            day=row.when.date(),
            store_name=row.store_name,
            line_type=row.line_type,
            category_id=row.category_id,
            category_name=row.category_name,
            item_id=row.item_id,
            name=row.name,
            quantity=row.quantity,
            unit=row.unit,
            unit_price=row.unit_price,
            total_price=row.total_price,
        )
        for row in rows
    ]


async def fetch_month(
    session: AsyncSession, group_id: uuid.UUID, year: int, month: int
) -> list[PurchaseRecord]:
    start, end = month_range(year, month)
    stmt, when = _base_query(group_id)
    stmt = stmt.where(when >= start, when < end)
    return await _rows_to_records(session, stmt)


async def fetch_item(
    session: AsyncSession, group_id: uuid.UUID, item_id: uuid.UUID
) -> list[PurchaseRecord]:
    stmt, _ = _base_query(group_id)
    stmt = stmt.where(LineItem.item_id == item_id)
    return await _rows_to_records(session, stmt)
