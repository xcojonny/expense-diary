"""Geldarithmetik — die Stelle, an der ADR-003 steht oder fällt."""

from __future__ import annotations

import pytest

from app.domain.money import (
    average_cents,
    parse_amount,
    parse_de_amount,
    parse_de_quantity,
    parse_quantity,
    share_bp,
    totals_match,
    unit_price_from_total,
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("1,09", 109),
        ("0,25", 25),
        ("-0,50", -50),
        ("1.234,56", 123456),
        ("12", 1200),
        ("1.099,00", 109900),
        ("3,49 €", 349),
        ("", None),
        ("kaputt", None),
    ],
)
def test_parse_de_amount(text: str, expected: int | None) -> None:
    assert parse_de_amount(text) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (3.49, 349),
        (3, 300),
        ("3.49", 349),
        ("3,49", 349),  # Modell hält sich nicht an den Prompt → trotzdem lesen
        ("1.234,56", 123456),  # Komma zuletzt → Dezimalkomma
        ("1,234.56", 123456),  # Punkt zuletzt → Dezimalpunkt
        (None, None),
        (True, None),  # bool ist keine Zahl
        ("", None),
    ],
)
def test_parse_amount(value: object, expected: int | None) -> None:
    assert parse_amount(value) == expected


def test_parse_amount_rounds_half_up() -> None:
    """Ein Modell, das 1.005 liefert, darf nicht auf 1,00 abrunden."""
    assert parse_amount("1.005") == 101
    assert parse_amount(0.014) == 1


def test_quantity_parsing_keeps_thousandths() -> None:
    assert parse_de_quantity("0,780") == 780
    assert parse_quantity(0.432) == 432
    assert parse_quantity(2) == 2000


def test_average_cents() -> None:
    assert average_cents([100, 200, 300]) == 200
    assert average_cents([100, 101]) == 101  # kaufmännisch aufrunden
    assert average_cents([]) is None


def test_share_bp() -> None:
    assert share_bp(2500, 10000) == 2500  # 25 % = 2500 Basispunkte
    assert share_bp(1, 3) == 3333
    assert share_bp(500, 0) is None


@pytest.mark.parametrize(
    ("item_sum", "printed", "expected"),
    [
        (471, 471, True),
        (471, 473, True),  # 2 Cent absolute Toleranz
        (471, 475, True),  # 1 % von 4,71 € = 4 Cent → noch drin
        (471, 480, False),
        (100, 103, False),  # bei kleinen Beträgen greift die 2-Cent-Grenze
        (100_00, 100_50, True),  # 1 % von 100 € = 1 €
        (100_00, 102_00, False),
    ],
)
def test_totals_match(item_sum: int, printed: int, expected: bool) -> None:
    assert totals_match(item_sum, printed) is expected


def test_unit_price_from_total() -> None:
    # 1,38 € für 0,780 kg → 1,77 €/kg
    assert unit_price_from_total(138, 780) == 177
    assert unit_price_from_total(298, 2000) == 149
    assert unit_price_from_total(100, None) is None
    assert unit_price_from_total(100, 0) is None
