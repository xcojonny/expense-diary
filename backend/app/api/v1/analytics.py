import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_group_id
from app.db.session import get_db
from app.domain import aggregation
from app.schemas.analytics import (
    ComparisonOut,
    ExpensiveItemsReportOut,
    ItemUsageOut,
    MonthlyReportOut,
    TrendPointOut,
)
from app.services import analytics_service

router = APIRouter(prefix="/analytics", tags=["analytics"])


def _resolve_month(year: int | None, month: int | None) -> tuple[int, int]:
    now = datetime.now(UTC)
    return year or now.year, month or now.month


@router.get("/monthly", response_model=MonthlyReportOut)
async def monthly(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    top_n: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> aggregation.MonthlyReport:
    y, m = _resolve_month(year, month)
    records = await analytics_service.fetch_month(db, group_id, y, m)
    return aggregation.monthly_report(records, year=y, month=m, top_n=top_n)


@router.get("/overbought", response_model=list[ItemUsageOut])
async def overbought(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> list[aggregation.ItemUsage]:
    y, m = _resolve_month(year, month)
    records = await analytics_service.fetch_month(db, group_id, y, m)
    return aggregation.overbought(records, limit=limit)


@router.get("/expensive", response_model=ExpensiveItemsReportOut)
async def expensive(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    limit: int = Query(default=10, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> aggregation.ExpensiveItemsReport:
    y, m = _resolve_month(year, month)
    records = await analytics_service.fetch_month(db, group_id, y, m)
    return aggregation.expensive_items(records, limit=limit)


@router.get("/compare", response_model=ComparisonOut)
async def compare(
    year: int | None = None,
    month: int | None = Query(default=None, ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> aggregation.Comparison:
    y, m = _resolve_month(year, month)
    py, pm = analytics_service.previous_month(y, m)
    current = await analytics_service.fetch_month(db, group_id, y, m)
    previous = await analytics_service.fetch_month(db, group_id, py, pm)
    return aggregation.compare(current, previous)


@router.get("/price-trend/{item_id}", response_model=list[TrendPointOut])
async def price_trend(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    group_id: uuid.UUID = Depends(get_current_group_id),
) -> list[aggregation.TrendPoint]:
    records = await analytics_service.fetch_item(db, group_id, item_id)
    return aggregation.price_trend(records)
