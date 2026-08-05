"""Auswertung — rein und I/O-frei. Das Herzstück der App.

Der Service holt die relevanten Positionen als flache `PurchaseRecord`s; alles
was *rechnet*, steht hier und ist ohne Datenbank testbar. Hier liegt der
Schwerpunkt der Unit-Tests.

Beträge sind Cent, Mengen Tausendstel, Anteile Basispunkte (ADR-003).
`is_food` kommt als Flag am Record — nicht mehr aus einer Namensliste im Code,
die beim Umbenennen einer Kategorie stillschweigend falsch wurde (ADR-007).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from app.domain.money import average_cents, share_bp

SortKey = Literal["frequency", "spend", "unit_price"]


@dataclass(frozen=True)
class PurchaseRecord:
    """Eine Bon-Position, flach angereichert mit dem Kontext, den die
    Auswertungen brauchen. `day` ist das wirksame Kaufdatum (`purchased_at`,
    sonst `created_at`)."""

    receipt_id: int
    day: date
    store_name: str | None
    kind: str  # product | deposit | discount
    category_id: int | None
    category_name: str | None
    is_food: bool
    item_id: int | None
    name: str
    quantity_milli: int | None
    unit: str | None
    unit_price_cents: int | None
    total_price_cents: int


UNCATEGORIZED = "Ohne Kategorie"
UNKNOWN_STORE = "Unbekannt"


def _products(records: list[PurchaseRecord]) -> list[PurchaseRecord]:
    return [r for r in records if r.kind == "product"]


def _group_by_item(records: list[PurchaseRecord]) -> dict[object, list[PurchaseRecord]]:
    """Produktpositionen je Artikel gruppieren.

    Schlüssel ist `item_id`; Positionen ohne Stammdatum fallen auf den
    kleingeschriebenen Namen zurück, damit sie trotzdem zusammenfinden.
    """
    groups: dict[object, list[PurchaseRecord]] = {}
    for record in _products(records):
        key: object = record.item_id if record.item_id is not None else record.name.lower()
        groups.setdefault(key, []).append(record)
    return groups


# --- Monatsbericht ------------------------------------------------------------


@dataclass
class CategorySpend:
    category_id: int | None
    category_name: str
    total_cents: int
    share_bp: int | None


@dataclass
class StoreSpend:
    store_name: str
    total_cents: int
    receipt_count: int


@dataclass
class TopLineItem:
    name: str
    total_price_cents: int
    day: date
    store_name: str | None


@dataclass
class MonthlyReport:
    year: int
    month: int
    receipt_count: int
    total_cents: int
    product_total_cents: int
    deposit_total_cents: int
    discount_total_cents: int
    food_total_cents: int
    by_category: list[CategorySpend] = field(default_factory=list)
    by_store: list[StoreSpend] = field(default_factory=list)
    top_items: list[TopLineItem] = field(default_factory=list)


def monthly_report(
    records: list[PurchaseRecord], *, year: int, month: int, top_n: int = 10
) -> MonthlyReport:
    """Gesamtausgaben, Aufschlüsselung nach Kategorie und Markt, teuerste
    Einzelpositionen. `records` muss bereits die Positionen des Monats sein."""
    by_kind: dict[str, int] = {"product": 0, "deposit": 0, "discount": 0}
    cat_totals: dict[tuple[int | None, str], int] = {}
    store_totals: dict[str, int] = {}
    store_receipts: dict[str, set[int]] = {}
    receipts: set[int] = set()

    for record in records:
        receipts.add(record.receipt_id)
        by_kind[record.kind] = by_kind.get(record.kind, 0) + record.total_price_cents
        store = record.store_name or UNKNOWN_STORE
        store_totals[store] = store_totals.get(store, 0) + record.total_price_cents
        store_receipts.setdefault(store, set()).add(record.receipt_id)
        if record.kind == "product":
            key = (record.category_id, record.category_name or UNCATEGORIZED)
            cat_totals[key] = cat_totals.get(key, 0) + record.total_price_cents

    product_total = by_kind["product"]
    by_category = sorted(
        (
            CategorySpend(cid, name, total, share_bp(total, product_total))
            for (cid, name), total in cat_totals.items()
        ),
        key=lambda c: c.total_cents,
        reverse=True,
    )
    by_store = sorted(
        (
            StoreSpend(name, total, len(store_receipts[name]))
            for name, total in store_totals.items()
        ),
        key=lambda s: s.total_cents,
        reverse=True,
    )
    top_items = [
        TopLineItem(r.name, r.total_price_cents, r.day, r.store_name)
        for r in sorted(_products(records), key=lambda r: r.total_price_cents, reverse=True)[:top_n]
    ]

    return MonthlyReport(
        year=year,
        month=month,
        receipt_count=len(receipts),
        total_cents=sum(r.total_price_cents for r in records),
        product_total_cents=product_total,
        deposit_total_cents=by_kind["deposit"],
        discount_total_cents=by_kind["discount"],
        food_total_cents=sum(r.total_price_cents for r in _products(records) if r.is_food),
        by_category=by_category,
        by_store=by_store,
        top_items=top_items,
    )


# --- Artikel-Ranking ----------------------------------------------------------
# Ein Endpoint statt zwei: „was kaufe ich zu oft“ (frequency), „teure
# Lebensmittel“ (spend) und „teuerster Stückpreis“ (unit_price) sind dieselbe
# Auswertung in drei Sortierungen.


@dataclass
class ItemStat:
    item_id: int | None
    name: str
    purchases: int  # wie oft gekauft
    total_quantity_milli: int
    unit: str | None
    total_spend_cents: int
    avg_unit_price_cents: int | None
    is_food: bool
    share_of_food_bp: int | None  # nur für Lebensmittel


@dataclass
class ItemRanking:
    food_total_cents: int
    sort: SortKey
    items: list[ItemStat] = field(default_factory=list)


def rank_items(
    records: list[PurchaseRecord], *, sort: SortKey = "spend", limit: int = 15
) -> ItemRanking:
    """Artikel gruppiert und sortiert — nach Häufigkeit, Ausgabe oder Stückpreis."""
    food_total = sum(r.total_price_cents for r in _products(records) if r.is_food)

    stats: list[ItemStat] = []
    for group in _group_by_item(records).values():
        head = group[0]
        units = Counter(r.unit for r in group if r.unit)
        prices = [r.unit_price_cents for r in group if r.unit_price_cents is not None]
        total_spend = sum(r.total_price_cents for r in group)
        stats.append(
            ItemStat(
                item_id=head.item_id,
                name=head.name,
                purchases=len(group),
                total_quantity_milli=sum(r.quantity_milli or 0 for r in group),
                unit=units.most_common(1)[0][0] if units else None,
                total_spend_cents=total_spend,
                avg_unit_price_cents=average_cents(prices),
                is_food=head.is_food,
                share_of_food_bp=share_bp(total_spend, food_total) if head.is_food else None,
            )
        )

    if sort == "frequency":
        # Häufigkeit zuerst, Ausgabe als Stichentscheid.
        stats.sort(key=lambda s: (s.purchases, s.total_spend_cents), reverse=True)
    elif sort == "unit_price":
        # Ohne Stückpreis gibt es nichts zu ranken → aus der Liste nehmen.
        stats = [s for s in stats if s.avg_unit_price_cents is not None]
        stats.sort(key=lambda s: (s.avg_unit_price_cents or 0, s.total_spend_cents), reverse=True)
    else:
        stats.sort(key=lambda s: s.total_spend_cents, reverse=True)

    return ItemRanking(food_total_cents=food_total, sort=sort, items=stats[:limit])


# --- Preisverlauf je Artikel --------------------------------------------------


@dataclass
class TrendPoint:
    day: date
    unit_price_cents: int
    purchases: int


def price_trend(records: list[PurchaseRecord]) -> list[TrendPoint]:
    """Ø-Stückpreis pro Tag für die Positionen *eines* Artikels, älteste zuerst.
    Positionen ohne Stückpreis werden übergangen."""
    by_day: dict[date, list[int]] = {}
    for record in _products(records):
        if record.unit_price_cents is not None:
            by_day.setdefault(record.day, []).append(record.unit_price_cents)

    points = [
        TrendPoint(day, average_cents(prices) or 0, len(prices))
        for day, prices in by_day.items()
    ]
    points.sort(key=lambda p: p.day)
    return points


# --- Vormonatsvergleich -------------------------------------------------------


@dataclass
class CategoryDelta:
    category_name: str
    current_cents: int
    previous_cents: int
    delta_cents: int


@dataclass
class Comparison:
    current_cents: int
    previous_cents: int
    delta_cents: int
    delta_bp: int | None  # None, wenn der Vormonat keine Ausgaben hatte
    by_category: list[CategoryDelta] = field(default_factory=list)


def _category_product_totals(records: list[PurchaseRecord]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for record in _products(records):
        name = record.category_name or UNCATEGORIZED
        totals[name] = totals.get(name, 0) + record.total_price_cents
    return totals


def compare(current: list[PurchaseRecord], previous: list[PurchaseRecord]) -> Comparison:
    """Gesamt- und Kategorieausgaben zwischen zwei Zeiträumen vergleichen."""
    current_total = sum(r.total_price_cents for r in current)
    previous_total = sum(r.total_price_cents for r in previous)
    delta = current_total - previous_total

    cur_cat = _category_product_totals(current)
    prev_cat = _category_product_totals(previous)
    by_category = [
        CategoryDelta(
            name,
            cur_cat.get(name, 0),
            prev_cat.get(name, 0),
            cur_cat.get(name, 0) - prev_cat.get(name, 0),
        )
        for name in sorted(set(cur_cat) | set(prev_cat))
    ]
    by_category.sort(key=lambda c: abs(c.delta_cents), reverse=True)

    return Comparison(
        current_cents=current_total,
        previous_cents=previous_total,
        delta_cents=delta,
        delta_bp=share_bp(delta, previous_total) if previous_total > 0 else None,
        by_category=by_category,
    )
