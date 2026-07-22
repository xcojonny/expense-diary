import uuid
from datetime import date
from decimal import Decimal

from app.domain.aggregation import (
    PurchaseRecord,
    compare,
    expensive_items,
    monthly_report,
    overbought,
    price_trend,
)

D = Decimal


def rec(
    *,
    total: str,
    line_type: str = "product",
    category: str | None = "Milchprodukte & Eier",
    name: str = "Bio Milch",
    item: uuid.UUID | None = None,
    qty: str | None = None,
    unit: str | None = None,
    unit_price: str | None = None,
    store: str | None = "REWE",
    day: date = date(2026, 7, 1),
    receipt: uuid.UUID | None = None,
) -> PurchaseRecord:
    return PurchaseRecord(
        receipt_id=receipt or uuid.uuid4(),
        day=day,
        store_name=store,
        line_type=line_type,
        category_id=None,
        category_name=category,
        item_id=item,
        name=name,
        quantity=D(qty) if qty else None,
        unit=unit,
        unit_price=D(unit_price) if unit_price else None,
        total_price=D(total),
    )


def test_monthly_report_totals_and_breakdowns() -> None:
    r1 = uuid.uuid4()
    records = [
        rec(total="1.29", name="Milch", category="Milchprodukte & Eier", receipt=r1),
        rec(total="0.25", line_type="deposit", category=None, name="PFAND", receipt=r1),
        rec(total="-0.50", line_type="discount", category=None, name="RABATT", receipt=r1),
        rec(total="2.00", name="Apfel", category="Obst & Gemüse", store="EDEKA"),
    ]
    report = monthly_report(records, year=2026, month=7, top_n=2)

    assert report.total_spending == D("3.04")  # 1.29 + 0.25 - 0.50 + 2.00
    assert report.product_total == D("3.29")
    assert report.deposit_total == D("0.25")
    assert report.discount_total == D("-0.50")
    assert report.receipt_count == 2  # r1 + the auto receipt of the apple line
    # by_category: products only, descending
    assert [(c.category_name, c.total) for c in report.by_category] == [
        ("Obst & Gemüse", D("2.00")),
        ("Milchprodukte & Eier", D("1.29")),
    ]
    # by_store descending; REWE's total nets deposit + discount to 1.04, below EDEKA's 2.00
    assert report.by_store[0].store_name == "EDEKA"
    assert report.by_store[0].total == D("2.00")
    rewe = next(s for s in report.by_store if s.store_name == "REWE")
    assert rewe.total == D("1.04")
    assert report.top_items[0].name == "Apfel"  # most expensive product first
    assert len(report.top_items) == 2  # top_n honored


def test_overbought_ranks_by_frequency() -> None:
    milk = uuid.uuid4()
    bread = uuid.uuid4()
    records = [
        rec(total="1.00", item=milk, name="Milch", qty="1", unit="stk"),
        rec(total="1.00", item=milk, name="Milch", qty="1", unit="stk"),
        rec(total="1.00", item=milk, name="Milch", qty="1", unit="stk"),
        rec(total="2.00", item=bread, name="Brot", qty="1", unit="stk"),
    ]
    result = overbought(records, limit=10)
    assert result[0].name == "Milch"
    assert result[0].count == 3
    assert result[0].total_quantity == D("3")
    assert result[0].unit == "stk"


def test_expensive_items_food_share_and_orderings() -> None:
    cheese = uuid.uuid4()
    soap = uuid.uuid4()
    records = [
        rec(total="10.00", item=cheese, name="Käse", category="Milchprodukte & Eier", unit_price="10.00"),
        rec(total="30.00", item=soap, name="Seife", category="Drogerie & Körperpflege", unit_price="3.00"),
    ]
    report = expensive_items(records, limit=10)

    # food_total counts only the cheese (soap is non-food)
    assert report.food_total == D("10.00")
    # by total spend: soap (30) before cheese (10)
    assert [i.name for i in report.by_total_spend] == ["Seife", "Käse"]
    cheese_item = next(i for i in report.by_total_spend if i.name == "Käse")
    assert cheese_item.share_of_food_budget == D("1")  # 10/10
    soap_item = next(i for i in report.by_total_spend if i.name == "Seife")
    assert soap_item.share_of_food_budget is None  # non-food → no share
    # by unit price: cheese (10.00) before soap (3.00)
    assert [i.name for i in report.by_unit_price] == ["Käse", "Seife"]


def test_price_trend_averages_per_day() -> None:
    item = uuid.uuid4()
    records = [
        rec(total="1.00", item=item, unit_price="1.00", day=date(2026, 6, 1)),
        rec(total="1.20", item=item, unit_price="1.20", day=date(2026, 6, 1)),
        rec(total="1.40", item=item, unit_price="1.40", day=date(2026, 7, 1)),
    ]
    points = price_trend(records)
    assert [p.day for p in points] == [date(2026, 6, 1), date(2026, 7, 1)]
    assert points[0].unit_price == D("1.1000")  # (1.00 + 1.20) / 2
    assert points[0].occurrences == 2


def test_compare_computes_delta_and_pct() -> None:
    current = [rec(total="120.00", category="Obst & Gemüse")]
    previous = [rec(total="100.00", category="Obst & Gemüse")]
    result = compare(current, previous)
    assert result.current_total == D("120.00")
    assert result.previous_total == D("100.00")
    assert result.delta == D("20.00")
    assert result.delta_pct == D("20.0")
    assert result.by_category[0].category_name == "Obst & Gemüse"
    assert result.by_category[0].delta == D("20.00")


def test_compare_without_previous_spend_has_no_pct() -> None:
    result = compare([rec(total="50.00")], [])
    assert result.previous_total == D("0")
    assert result.delta_pct is None
