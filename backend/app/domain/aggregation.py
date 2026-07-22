"""Analysis-layer aggregation — pure, I/O-free logic (the heart of the app).

The service fetches the relevant line items into ``PurchaseRecord``s; everything
that *computes* a report lives here so it is unit-testable without a database.
This is where the test coverage concentrates.
"""

import uuid
from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

# Categories that are not food, so they are excluded from the "food budget"
# share. Uncategorized products (category_name None) are also left out of the
# food total because their nature is unknown.
NON_FOOD_CATEGORIES = frozenset(
    {
        "Haushalt & Reinigung",
        "Drogerie & Körperpflege",
        "Tierbedarf",
        "Baby & Kind",
        "Sonstiges",
    }
)

_ZERO = Decimal(0)
_PRICE_Q = Decimal("0.0001")


@dataclass(frozen=True)
class PurchaseRecord:
    """One receipt line, flattened with the receipt/category/item context the
    aggregations need. ``day`` is the effective purchase date (purchased_at, or
    created_at as a fallback)."""

    receipt_id: uuid.UUID
    day: date
    store_name: str | None
    line_type: str  # product | deposit | discount
    category_id: uuid.UUID | None
    category_name: str | None
    item_id: uuid.UUID | None
    name: str
    quantity: Decimal | None
    unit: str | None
    unit_price: Decimal | None
    total_price: Decimal


def is_food(category_name: str | None) -> bool:
    return category_name is not None and category_name not in NON_FOOD_CATEGORIES


def _products(records: list[PurchaseRecord]) -> list[PurchaseRecord]:
    return [r for r in records if r.line_type == "product"]


# --- Monthly report -----------------------------------------------------------


@dataclass
class CategorySpend:
    category_id: uuid.UUID | None
    category_name: str
    total: Decimal


@dataclass
class StoreSpend:
    store_name: str
    total: Decimal


@dataclass
class TopLineItem:
    name: str
    total_price: Decimal
    day: date
    store_name: str | None


@dataclass
class MonthlyReport:
    year: int
    month: int
    receipt_count: int
    total_spending: Decimal
    product_total: Decimal
    deposit_total: Decimal
    discount_total: Decimal
    by_category: list[CategorySpend] = field(default_factory=list)
    by_store: list[StoreSpend] = field(default_factory=list)
    top_items: list[TopLineItem] = field(default_factory=list)


def monthly_report(
    records: list[PurchaseRecord], *, year: int, month: int, top_n: int = 10
) -> MonthlyReport:
    """Total spend, per-category and per-store breakdowns, and the most
    expensive single positions. ``records`` must already be the month's lines."""
    by_type: dict[str, Decimal] = {"product": _ZERO, "deposit": _ZERO, "discount": _ZERO}
    cat_totals: dict[tuple[uuid.UUID | None, str], Decimal] = {}
    store_totals: dict[str, Decimal] = {}
    receipts: set[uuid.UUID] = set()

    for r in records:
        receipts.add(r.receipt_id)
        by_type[r.line_type] = by_type.get(r.line_type, _ZERO) + r.total_price
        store = r.store_name or "Unbekannt"
        store_totals[store] = store_totals.get(store, _ZERO) + r.total_price
        if r.line_type == "product":
            key = (r.category_id, r.category_name or "Ohne Kategorie")
            cat_totals[key] = cat_totals.get(key, _ZERO) + r.total_price

    by_category = sorted(
        (CategorySpend(cid, cname, total) for (cid, cname), total in cat_totals.items()),
        key=lambda c: c.total,
        reverse=True,
    )
    by_store = sorted(
        (StoreSpend(name, total) for name, total in store_totals.items()),
        key=lambda s: s.total,
        reverse=True,
    )
    top_items = [
        TopLineItem(r.name, r.total_price, r.day, r.store_name)
        for r in sorted(_products(records), key=lambda r: r.total_price, reverse=True)[:top_n]
    ]

    return MonthlyReport(
        year=year,
        month=month,
        receipt_count=len(receipts),
        total_spending=sum((r.total_price for r in records), _ZERO),
        product_total=by_type["product"],
        deposit_total=by_type["deposit"],
        discount_total=by_type["discount"],
        by_category=by_category,
        by_store=by_store,
        top_items=top_items,
    )


# --- "What do I buy too much of" ---------------------------------------------


@dataclass
class ItemUsage:
    item_id: uuid.UUID | None
    name: str
    count: int  # how many times bought
    total_quantity: Decimal
    unit: str | None
    total_spend: Decimal


# Group by item_id, falling back to the lowercased name so lines that never
# got mapped to an Item still group together.
def _group_products_by_item(
    records: list[PurchaseRecord],
) -> dict[object, list[PurchaseRecord]]:
    groups: dict[object, list[PurchaseRecord]] = {}
    for r in _products(records):
        key: object = r.item_id if r.item_id is not None else r.name.lower()
        groups.setdefault(key, []).append(r)
    return groups


def overbought(records: list[PurchaseRecord], *, limit: int = 10) -> list[ItemUsage]:
    """Items ranked by purchase frequency (then total spend) in the period."""
    usages: list[ItemUsage] = []
    for group in _group_products_by_item(records).values():
        units = Counter(r.unit for r in group if r.unit)
        usages.append(
            ItemUsage(
                item_id=group[0].item_id,
                name=group[0].name,
                count=len(group),
                total_quantity=sum((r.quantity or _ZERO for r in group), _ZERO),
                unit=units.most_common(1)[0][0] if units else None,
                total_spend=sum((r.total_price for r in group), _ZERO),
            )
        )
    usages.sort(key=lambda u: (u.count, u.total_spend), reverse=True)
    return usages[:limit]


# --- "Expensive food" ---------------------------------------------------------


@dataclass
class ExpensiveItem:
    item_id: uuid.UUID | None
    name: str
    total_spend: Decimal
    avg_unit_price: Decimal | None
    occurrences: int
    share_of_food_budget: Decimal | None  # fraction 0..1, only for food items


@dataclass
class ExpensiveItemsReport:
    food_total: Decimal
    by_total_spend: list[ExpensiveItem] = field(default_factory=list)
    by_unit_price: list[ExpensiveItem] = field(default_factory=list)


def expensive_items(records: list[PurchaseRecord], *, limit: int = 10) -> ExpensiveItemsReport:
    """Items by total spend and by unit price, with each food item's share of
    the month's food budget."""
    food_total = sum(
        (r.total_price for r in _products(records) if is_food(r.category_name)), _ZERO
    )

    items: list[ExpensiveItem] = []
    for group in _group_products_by_item(records).values():
        prices = [r.unit_price for r in group if r.unit_price is not None]
        avg_price = (
            (sum(prices, _ZERO) / len(prices)).quantize(_PRICE_Q) if prices else None
        )
        total_spend = sum((r.total_price for r in group), _ZERO)
        food = is_food(group[0].category_name)
        share = (
            (total_spend / food_total) if food and food_total > _ZERO else None
        )
        items.append(
            ExpensiveItem(
                item_id=group[0].item_id,
                name=group[0].name,
                total_spend=total_spend,
                avg_unit_price=avg_price,
                occurrences=len(group),
                share_of_food_budget=share,
            )
        )

    by_total_spend = sorted(items, key=lambda i: i.total_spend, reverse=True)[:limit]
    by_unit_price = sorted(
        (i for i in items if i.avg_unit_price is not None),
        key=lambda i: i.avg_unit_price or _ZERO,
        reverse=True,
    )[:limit]
    return ExpensiveItemsReport(
        food_total=food_total, by_total_spend=by_total_spend, by_unit_price=by_unit_price
    )


# --- Price trend per item -----------------------------------------------------


@dataclass
class TrendPoint:
    day: date
    unit_price: Decimal
    occurrences: int


def price_trend(records: list[PurchaseRecord]) -> list[TrendPoint]:
    """Average unit price per day for one item's product lines, oldest first.
    Lines without a unit price are ignored."""
    by_day: dict[date, list[Decimal]] = {}
    for r in _products(records):
        if r.unit_price is not None:
            by_day.setdefault(r.day, []).append(r.unit_price)
    points = [
        TrendPoint(day, (sum(prices, _ZERO) / len(prices)).quantize(_PRICE_Q), len(prices))
        for day, prices in by_day.items()
    ]
    points.sort(key=lambda p: p.day)
    return points


# --- Previous-month comparison ------------------------------------------------


@dataclass
class CategoryDelta:
    category_name: str
    current: Decimal
    previous: Decimal
    delta: Decimal


@dataclass
class Comparison:
    current_total: Decimal
    previous_total: Decimal
    delta: Decimal
    delta_pct: Decimal | None  # None when the previous month had no spend
    by_category: list[CategoryDelta] = field(default_factory=list)


def _category_product_totals(records: list[PurchaseRecord]) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = {}
    for r in _products(records):
        name = r.category_name or "Ohne Kategorie"
        totals[name] = totals.get(name, _ZERO) + r.total_price
    return totals


def compare(
    current: list[PurchaseRecord], previous: list[PurchaseRecord]
) -> Comparison:
    """Compare total and per-category spend between the current and previous
    month's records."""
    current_total = sum((r.total_price for r in current), _ZERO)
    previous_total = sum((r.total_price for r in previous), _ZERO)
    delta = current_total - previous_total
    delta_pct = (
        (delta / previous_total * 100).quantize(Decimal("0.1"))
        if previous_total > _ZERO
        else None
    )

    cur_cat = _category_product_totals(current)
    prev_cat = _category_product_totals(previous)
    by_category = [
        CategoryDelta(name, cur_cat.get(name, _ZERO), prev_cat.get(name, _ZERO),
                      cur_cat.get(name, _ZERO) - prev_cat.get(name, _ZERO))
        for name in sorted(set(cur_cat) | set(prev_cat))
    ]
    by_category.sort(key=lambda c: abs(c.delta), reverse=True)

    return Comparison(
        current_total=current_total,
        previous_total=previous_total,
        delta=delta,
        delta_pct=delta_pct,
        by_category=by_category,
    )
