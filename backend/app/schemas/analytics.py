import uuid
from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class _FromAttrs(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class CategorySpendOut(_FromAttrs):
    category_id: uuid.UUID | None
    category_name: str
    total: Decimal


class StoreSpendOut(_FromAttrs):
    store_name: str
    total: Decimal


class TopLineItemOut(_FromAttrs):
    name: str
    total_price: Decimal
    day: date
    store_name: str | None


class MonthlyReportOut(_FromAttrs):
    year: int
    month: int
    receipt_count: int
    total_spending: Decimal
    product_total: Decimal
    deposit_total: Decimal
    discount_total: Decimal
    by_category: list[CategorySpendOut]
    by_store: list[StoreSpendOut]
    top_items: list[TopLineItemOut]


class ItemUsageOut(_FromAttrs):
    item_id: uuid.UUID | None
    name: str
    count: int
    total_quantity: Decimal
    unit: str | None
    total_spend: Decimal


class ExpensiveItemOut(_FromAttrs):
    item_id: uuid.UUID | None
    name: str
    total_spend: Decimal
    avg_unit_price: Decimal | None
    occurrences: int
    share_of_food_budget: Decimal | None


class ExpensiveItemsReportOut(_FromAttrs):
    food_total: Decimal
    by_total_spend: list[ExpensiveItemOut]
    by_unit_price: list[ExpensiveItemOut]


class TrendPointOut(_FromAttrs):
    day: date
    unit_price: Decimal
    occurrences: int


class CategoryDeltaOut(_FromAttrs):
    category_name: str
    current: Decimal
    previous: Decimal
    delta: Decimal


class ComparisonOut(_FromAttrs):
    current_total: Decimal
    previous_total: Decimal
    delta: Decimal
    delta_pct: Decimal | None
    by_category: list[CategoryDeltaOut]
