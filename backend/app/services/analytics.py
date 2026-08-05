"""Datenzugriff für die Auswertung — die Rechnerei steckt in `domain/aggregation`.

Diese Datei holt Positionen als flache `PurchaseRecord`s und ruft damit die
reinen Funktionen auf. Alles hier ist SQL, dort ist alles testbar ohne DB.
"""

from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain import aggregation as agg
from app.models import Category, Item, LineItem, Receipt, ReceiptStatus

# `needs_review` zählt mit: ein ungeprüfter Bon hat echte Positionen, und ihn
# auszublenden würde einen ganzen Einkauf aus dem Monatstotal nehmen — der
# Bericht wäre stillschweigend zu niedrig. Stattdessen weist die API die Anzahl
# ungeprüfter Bons aus, damit die UI daran erinnern kann.
ANALYZED_STATUSES = (ReceiptStatus.DONE.value, ReceiptStatus.NEEDS_REVIEW.value)

def effective_date() -> sa.ColumnElement[datetime]:
    """Wirksames Kaufdatum: `purchased_at` vom Bon, sonst der Upload-Zeitpunkt.

    `coalesce` übernimmt den Typ des ersten Arguments, liefert also ein datetime
    und nicht den rohen SQLite-String.
    """
    return sa.func.coalesce(Receipt.purchased_at, Receipt.created_at)


def month_range(year: int, month: int) -> tuple[datetime, datetime]:
    """`[start, ende)` eines Monats — halboffen, damit kein Tag doppelt zählt."""
    start = datetime(year, month, 1)
    end = datetime(year + 1, 1, 1) if month == 12 else datetime(year, month + 1, 1)
    return start, end


def previous_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _record_query(household_id: int) -> sa.Select[tuple[object, ...]]:
    return (
        sa.select(
            LineItem.receipt_id,
            effective_date().label("day"),
            Receipt.store_name,
            LineItem.kind,
            LineItem.category_id,
            Category.name.label("category_name"),
            Category.is_food,
            LineItem.item_id,
            LineItem.name,
            LineItem.quantity_milli,
            LineItem.unit,
            LineItem.unit_price_cents,
            LineItem.total_price_cents,
        )
        .join(Receipt, LineItem.receipt_id == Receipt.id)
        .outerjoin(Category, LineItem.category_id == Category.id)
        .where(Receipt.household_id == household_id, Receipt.status.in_(ANALYZED_STATUSES))
    )


async def fetch_records(
    session: AsyncSession,
    *,
    household_id: int,
    start: datetime,
    end: datetime,
    item_id: int | None = None,
) -> list[agg.PurchaseRecord]:
    query = _record_query(household_id).where(
        effective_date() >= start, effective_date() < end
    )
    if item_id is not None:
        query = query.where(LineItem.item_id == item_id)

    rows = (await session.execute(query)).all()
    return [
        agg.PurchaseRecord(
            receipt_id=row.receipt_id,
            day=row.day.date(),
            store_name=row.store_name,
            kind=row.kind,
            category_id=row.category_id,
            category_name=row.category_name,
            # Ohne Kategorie ist die Natur unbekannt — dann nicht ins
            # Lebensmittelbudget zählen.
            is_food=bool(row.is_food),
            item_id=row.item_id,
            name=row.name,
            quantity_milli=row.quantity_milli,
            unit=row.unit,
            unit_price_cents=row.unit_price_cents,
            total_price_cents=row.total_price_cents,
        )
        for row in rows
    ]


async def count_receipts(
    session: AsyncSession, *, household_id: int, start: datetime, end: datetime
) -> int:
    """Bons im Zeitraum — auch solche ohne erkannte Positionen.

    Die Aggregation zählt nur Bons, die Positionen beigesteuert haben; für die
    Anzeige ist die Zahl aller Bons die wahrheitsgemäße.
    """
    return (
        await session.execute(
            sa.select(sa.func.count(Receipt.id)).where(
                Receipt.household_id == household_id,
                Receipt.status.in_(ANALYZED_STATUSES),
                effective_date() >= start,
                effective_date() < end,
            )
        )
    ).scalar_one()


async def count_unreviewed(
    session: AsyncSession, *, household_id: int, start: datetime, end: datetime
) -> int:
    return (
        await session.execute(
            sa.select(sa.func.count(Receipt.id)).where(
                Receipt.household_id == household_id,
                Receipt.status == ReceiptStatus.NEEDS_REVIEW.value,
                effective_date() >= start,
                effective_date() < end,
            )
        )
    ).scalar_one()


async def monthly(
    session: AsyncSession, *, household_id: int, year: int, month: int
) -> agg.MonthlyReport:
    start, end = month_range(year, month)
    records = await fetch_records(session, household_id=household_id, start=start, end=end)
    return agg.monthly_report(records, year=year, month=month)


async def compare_to_previous(
    session: AsyncSession, *, household_id: int, year: int, month: int
) -> agg.Comparison:
    start, end = month_range(year, month)
    prev_year, prev_month = previous_month(year, month)
    prev_start, prev_end = month_range(prev_year, prev_month)
    return agg.compare(
        await fetch_records(session, household_id=household_id, start=start, end=end),
        await fetch_records(session, household_id=household_id, start=prev_start, end=prev_end),
    )


async def item_ranking(
    session: AsyncSession,
    *,
    household_id: int,
    year: int,
    month: int,
    sort: agg.SortKey,
    limit: int,
) -> agg.ItemRanking:
    start, end = month_range(year, month)
    records = await fetch_records(session, household_id=household_id, start=start, end=end)
    return agg.rank_items(records, sort=sort, limit=limit)


async def price_trend(
    session: AsyncSession, *, household_id: int, item_id: int, months: int = 12
) -> list[agg.TrendPoint]:
    """Preisverlauf über die letzten `months` Monate — der Zeitraum ist hier
    absichtlich länger als ein Monat, weil ein Trend genau das braucht."""
    today = datetime.now()
    _, end = month_range(today.year, today.month)
    year, month = today.year, today.month
    for _ in range(max(0, months - 1)):
        year, month = previous_month(year, month)
    start, _ = month_range(year, month)

    records = await fetch_records(
        session, household_id=household_id, start=start, end=end, item_id=item_id
    )
    return agg.price_trend(records)


async def get_item(session: AsyncSession, item_id: int, *, household_id: int) -> Item | None:
    """Artikel nur innerhalb des Haushalts — sonst wäre `/price-trend/{item_id}`
    ein Weg, fremde Preisverläufe zu lesen."""
    return (
        await session.execute(
            sa.select(Item).where(Item.id == item_id, Item.household_id == household_id)
        )
    ).scalar_one_or_none()
