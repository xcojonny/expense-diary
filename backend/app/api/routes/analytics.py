"""Auswertung — das Herzstück, als API.

Das Artikel-Ranking ist **ein** Endpoint mit `sort=`, nicht zwei getrennte:
„was kaufe ich zu oft", „teure Lebensmittel" und „teuerster Stückpreis" sind
dieselbe Auswertung in drei Sortierungen.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import AuthDep, SessionDep
from app.schemas import (
    CategoryDeltaOut,
    CategorySpendOut,
    ComparisonOut,
    ItemRankingOut,
    ItemStatOut,
    MonthlyReportOut,
    PriceTrendOut,
    StoreSpendOut,
    TopLineItemOut,
    TrendPointOut,
)
from app.services import analytics as analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])

YearQuery = Annotated[int | None, Query(ge=2000, le=2100)]
MonthQuery = Annotated[int | None, Query(ge=1, le=12)]


def _resolve_month(year: int | None, month: int | None) -> tuple[int, int]:
    """Default ist der laufende Monat."""
    now = datetime.now()
    return year or now.year, month or now.month


@router.get("/monthly", response_model=MonthlyReportOut)
async def monthly(
    session: SessionDep, _auth: AuthDep, year: YearQuery = None, month: MonthQuery = None
) -> MonthlyReportOut:
    resolved_year, resolved_month = _resolve_month(year, month)
    report = await analytics_service.monthly(session, year=resolved_year, month=resolved_month)
    start, end = analytics_service.month_range(resolved_year, resolved_month)
    unreviewed = await analytics_service.count_unreviewed(session, start=start, end=end)

    return MonthlyReportOut(
        year=report.year,
        month=report.month,
        receipt_count=report.receipt_count,
        unreviewed_count=unreviewed,
        total_cents=report.total_cents,
        product_total_cents=report.product_total_cents,
        deposit_total_cents=report.deposit_total_cents,
        discount_total_cents=report.discount_total_cents,
        food_total_cents=report.food_total_cents,
        by_category=[
            CategorySpendOut(
                category_id=c.category_id,
                category_name=c.category_name,
                total_cents=c.total_cents,
                share_bp=c.share_bp,
            )
            for c in report.by_category
        ],
        by_store=[
            StoreSpendOut(
                store_name=s.store_name,
                total_cents=s.total_cents,
                receipt_count=s.receipt_count,
            )
            for s in report.by_store
        ],
        top_items=[
            TopLineItemOut(
                name=t.name,
                total_price_cents=t.total_price_cents,
                day=t.day,
                store_name=t.store_name,
            )
            for t in report.top_items
        ],
    )


@router.get("/compare", response_model=ComparisonOut)
async def compare(
    session: SessionDep, _auth: AuthDep, year: YearQuery = None, month: MonthQuery = None
) -> ComparisonOut:
    resolved_year, resolved_month = _resolve_month(year, month)
    result = await analytics_service.compare_to_previous(
        session, year=resolved_year, month=resolved_month
    )
    return ComparisonOut(
        current_cents=result.current_cents,
        previous_cents=result.previous_cents,
        delta_cents=result.delta_cents,
        delta_bp=result.delta_bp,
        by_category=[
            CategoryDeltaOut(
                category_name=c.category_name,
                current_cents=c.current_cents,
                previous_cents=c.previous_cents,
                delta_cents=c.delta_cents,
            )
            for c in result.by_category
        ],
    )


@router.get("/items", response_model=ItemRankingOut)
async def items(
    session: SessionDep,
    _auth: AuthDep,
    year: YearQuery = None,
    month: MonthQuery = None,
    sort: Literal["frequency", "spend", "unit_price"] = "spend",
    limit: Annotated[int, Query(ge=1, le=100)] = 15,
) -> ItemRankingOut:
    resolved_year, resolved_month = _resolve_month(year, month)
    ranking = await analytics_service.item_ranking(
        session, year=resolved_year, month=resolved_month, sort=sort, limit=limit
    )
    return ItemRankingOut(
        food_total_cents=ranking.food_total_cents,
        sort=ranking.sort,
        items=[
            ItemStatOut(
                item_id=i.item_id,
                name=i.name,
                purchases=i.purchases,
                total_quantity_milli=i.total_quantity_milli,
                unit=i.unit,
                total_spend_cents=i.total_spend_cents,
                avg_unit_price_cents=i.avg_unit_price_cents,
                is_food=i.is_food,
                share_of_food_bp=i.share_of_food_bp,
            )
            for i in ranking.items
        ],
    )


@router.get("/price-trend/{item_id}", response_model=PriceTrendOut)
async def price_trend(
    session: SessionDep,
    _auth: AuthDep,
    item_id: int,
    months: Annotated[int, Query(ge=1, le=60)] = 12,
) -> PriceTrendOut:
    item = await analytics_service.get_item(session, item_id)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Artikel nicht gefunden.")
    points = await analytics_service.price_trend(session, item_id=item_id, months=months)
    return PriceTrendOut(
        item_id=item_id,
        name=item.display_name,
        points=[
            TrendPointOut(day=p.day, unit_price_cents=p.unit_price_cents, purchases=p.purchases)
            for p in points
        ],
    )
