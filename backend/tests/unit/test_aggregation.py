"""Auswertungslogik — das Herzstück, ohne Datenbank."""

from __future__ import annotations

from datetime import date

from app.domain.aggregation import (
    PurchaseRecord,
    compare,
    monthly_report,
    price_trend,
    rank_items,
)


def record(
    *,
    name: str = "H-Milch",
    total: int = 109,
    kind: str = "product",
    category: str | None = "Milchprodukte & Eier",
    is_food: bool = True,
    item_id: int | None = 1,
    day: date | None = None,
    store: str | None = "REWE",
    unit_price: int | None = 109,
    quantity: int | None = 1000,
    receipt_id: int = 1,
    category_id: int | None = 2,
) -> PurchaseRecord:
    return PurchaseRecord(
        receipt_id=receipt_id,
        day=day or date(2026, 3, 4),
        store_name=store,
        kind=kind,
        category_id=category_id if category else None,
        category_name=category,
        is_food=is_food,
        item_id=item_id,
        name=name,
        quantity_milli=quantity,
        unit="stk",
        unit_price_cents=unit_price,
        total_price_cents=total,
    )


# --- Monatsbericht ------------------------------------------------------------


def test_monthly_report_totals_by_kind() -> None:
    records = [
        record(total=109),
        record(name="Butter", total=249, item_id=2),
        record(name="PFAND", total=25, kind="deposit", category=None, item_id=None),
        record(name="RABATT", total=-50, kind="discount", category=None, item_id=None),
    ]
    report = monthly_report(records, year=2026, month=3)

    assert report.total_cents == 333  # 109 + 249 + 25 - 50
    assert report.product_total_cents == 358
    assert report.deposit_total_cents == 25
    assert report.discount_total_cents == -50
    assert report.receipt_count == 1


def test_monthly_report_category_breakdown_with_shares() -> None:
    records = [
        record(total=300, category="Obst", category_id=1),
        record(total=100, category="Gemüse", category_id=2, item_id=2),
    ]
    report = monthly_report(records, year=2026, month=3)

    assert [(c.category_name, c.total_cents, c.share_bp) for c in report.by_category] == [
        ("Obst", 300, 7500),  # 75 %
        ("Gemüse", 100, 2500),
    ]


def test_monthly_report_uncategorized_bucket() -> None:
    report = monthly_report([record(category=None, category_id=None)], year=2026, month=3)
    assert report.by_category[0].category_name == "Ohne Kategorie"


def test_monthly_report_store_breakdown_counts_receipts() -> None:
    records = [
        record(store="REWE", receipt_id=1, total=100),
        record(store="REWE", receipt_id=2, total=200, item_id=2),
        record(store=None, receipt_id=3, total=50, item_id=3),
    ]
    report = monthly_report(records, year=2026, month=3)

    assert [(s.store_name, s.total_cents, s.receipt_count) for s in report.by_store] == [
        ("REWE", 300, 2),
        ("Unbekannt", 50, 1),
    ]


def test_monthly_report_food_total_excludes_non_food() -> None:
    """`is_food` kommt am Record, nicht aus einer Namensliste (ADR-007)."""
    records = [
        record(total=500, is_food=True),
        record(name="Spüli", total=200, is_food=False, category="Haushalt", item_id=2),
    ]
    assert monthly_report(records, year=2026, month=3).food_total_cents == 500


def test_monthly_report_top_items_sorted_and_capped() -> None:
    records = [record(name=f"A{i}", total=i * 100, item_id=i) for i in range(1, 6)]
    report = monthly_report(records, year=2026, month=3, top_n=2)
    assert [t.name for t in report.top_items] == ["A5", "A4"]


# --- Artikel-Ranking ----------------------------------------------------------


def test_rank_items_by_frequency() -> None:
    records = [
        *[record(name="Milch", item_id=1, total=100) for _ in range(3)],
        *[record(name="Butter", item_id=2, total=900) for _ in range(2)],
    ]
    ranking = rank_items(records, sort="frequency")
    assert [(i.name, i.purchases) for i in ranking.items] == [("Milch", 3), ("Butter", 2)]


def test_rank_items_by_spend() -> None:
    records = [
        *[record(name="Milch", item_id=1, total=100) for _ in range(3)],
        record(name="Butter", item_id=2, total=900),
    ]
    ranking = rank_items(records, sort="spend")
    assert [(i.name, i.total_spend_cents) for i in ranking.items] == [("Butter", 900), ("Milch", 300)]


def test_rank_items_by_unit_price_drops_items_without_one() -> None:
    records = [
        record(name="Trüffel", item_id=1, unit_price=9900, total=9900),
        record(name="Milch", item_id=2, unit_price=109, total=109),
        record(name="Unbekannt", item_id=3, unit_price=None, total=500),
    ]
    ranking = rank_items(records, sort="unit_price")
    assert [i.name for i in ranking.items] == ["Trüffel", "Milch"]


def test_rank_items_averages_unit_price() -> None:
    records = [
        record(name="Milch", item_id=1, unit_price=100, total=100),
        record(name="Milch", item_id=1, unit_price=120, total=120),
    ]
    assert rank_items(records).items[0].avg_unit_price_cents == 110


def test_rank_items_groups_unmapped_lines_by_name() -> None:
    """Positionen ohne Stammdatum müssen trotzdem zusammenfinden."""
    records = [
        record(name="Rhabarber", item_id=None, total=100),
        record(name="rhabarber", item_id=None, total=200),
    ]
    ranking = rank_items(records)
    assert len(ranking.items) == 1
    assert ranking.items[0].total_spend_cents == 300


def test_rank_items_food_share() -> None:
    records = [
        record(name="Milch", item_id=1, total=250, is_food=True),
        record(name="Butter", item_id=2, total=750, is_food=True),
        record(name="Spüli", item_id=3, total=500, is_food=False),
    ]
    ranking = rank_items(records)
    assert ranking.food_total_cents == 1000
    shares = {i.name: i.share_of_food_bp for i in ranking.items}
    assert shares["Butter"] == 7500  # 75 % des Lebensmittelbudgets
    assert shares["Milch"] == 2500
    assert shares["Spüli"] is None  # kein Lebensmittel → kein Anteil


def test_rank_items_ignores_deposit_and_discount() -> None:
    records = [
        record(name="Milch", item_id=1, total=100),
        record(name="PFAND", kind="deposit", item_id=None, total=25),
    ]
    assert [i.name for i in rank_items(records).items] == ["Milch"]


# --- Preisverlauf -------------------------------------------------------------


def test_price_trend_averages_per_day_and_sorts() -> None:
    records = [
        record(day=date(2026, 3, 10), unit_price=120),
        record(day=date(2026, 3, 1), unit_price=100),
        record(day=date(2026, 3, 1), unit_price=110),
    ]
    points = price_trend(records)
    assert [(p.day.isoformat(), p.unit_price_cents, p.purchases) for p in points] == [
        ("2026-03-01", 105, 2),
        ("2026-03-10", 120, 1),
    ]


def test_price_trend_skips_lines_without_unit_price() -> None:
    assert price_trend([record(unit_price=None)]) == []


# --- Vormonatsvergleich -------------------------------------------------------


def test_compare_computes_delta_in_basis_points() -> None:
    result = compare([record(total=1200)], [record(total=1000)])
    assert result.delta_cents == 200
    assert result.delta_bp == 2000  # +20 %


def test_compare_without_previous_spend_has_no_percentage() -> None:
    result = compare([record(total=1200)], [])
    assert result.delta_cents == 1200
    assert result.delta_bp is None


def test_compare_lists_categories_by_absolute_change() -> None:
    current = [
        record(total=500, category="Obst", category_id=1),
        record(total=100, category="Gemüse", category_id=2, item_id=2),
    ]
    previous = [record(total=100, category="Obst", category_id=1)]
    result = compare(current, previous)

    assert [(c.category_name, c.delta_cents) for c in result.by_category] == [
        ("Obst", 400),
        ("Gemüse", 100),
    ]
