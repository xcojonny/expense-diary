"""Beide Extraktionswege — Textparser und Modell-JSON."""

from __future__ import annotations

import json

import pytest

from app.domain.extraction import (
    ExtractionError,
    ParsedLineItem,
    ParsedReceipt,
    guess_category,
    parse_receipt_json,
    parse_receipt_text,
    reconcile,
)
from tests.conftest import REWE_RECEIPT_LINES

# --- Textparser (eBon, ohne Modell) ------------------------------------------


@pytest.fixture
def rewe() -> ParsedReceipt:
    return parse_receipt_text("\n".join(REWE_RECEIPT_LINES))


def test_text_parser_reads_store_and_total(rewe: ParsedReceipt) -> None:
    assert rewe.store_name == "REWE"
    assert rewe.total_cents == 471


def test_text_parser_reads_date_and_time(rewe: ParsedReceipt) -> None:
    assert rewe.purchased_at is not None
    assert rewe.purchased_at.isoformat() == "2026-03-04T17:42:00"


def test_text_parser_finds_all_lines(rewe: ParsedReceipt) -> None:
    assert [(i.name, i.total_price_cents) for i in rewe.items] == [
        ("H-MILCH 3,5%", 109),
        ("BUTTER MILDGES.", 249),
        ("BANANEN", 138),
        ("PFAND 0,25", 25),
        ("RABATT AKTION", -50),
    ]


def test_text_parser_classifies_deposit_and_discount(rewe: ParsedReceipt) -> None:
    kinds = {i.name: i.kind for i in rewe.items}
    assert kinds["PFAND 0,25"] == "deposit"
    assert kinds["RABATT AKTION"] == "discount"
    assert kinds["H-MILCH 3,5%"] == "product"


def test_text_parser_attaches_weight_line(rewe: ParsedReceipt) -> None:
    """Die Folgezeile "0,780 kg x 1,77" gehört zu den Bananen darüber."""
    bananas = next(i for i in rewe.items if i.name == "BANANEN")
    assert bananas.quantity_milli == 780
    assert bananas.unit == "kg"
    assert bananas.unit_price_cents == 177


def test_text_parser_stops_at_total(rewe: ParsedReceipt) -> None:
    """"Geg. BAR 5,00" steht unter SUMME und darf keine Position werden."""
    assert not any("BAR" in i.name for i in rewe.items)


def test_text_parser_item_sum_matches_printed_total(rewe: ParsedReceipt) -> None:
    assert rewe.item_sum_cents == rewe.total_cents
    confidence, needs_review = reconcile(rewe)
    assert (confidence, needs_review) == ("high", False)


def test_text_parser_inline_quantity_lidl_style() -> None:
    text = "LIDL PLUS\nJOGHURT              0,29 x 6            1,74 B\nzu zahlen            1,74"
    parsed = parse_receipt_text(text)
    assert parsed.store_name == "Lidl"
    assert len(parsed.items) == 1
    item = parsed.items[0]
    assert (item.quantity_milli, item.unit_price_cents, item.total_price_cents) == (6000, 29, 174)


def test_text_parser_unknown_layout_is_low_confidence() -> None:
    parsed = parse_receipt_text("nur irgendein Fließtext ohne Beträge")
    assert parsed.confidence == "low"
    assert reconcile(parsed) == ("low", True)


# --- Modell-JSON --------------------------------------------------------------


def _payload(**overrides: object) -> str:
    data: dict[str, object] = {
        "store_name": "EDEKA",
        "purchased_at": "2026-03-04",
        "currency": "EUR",
        "total": 4.71,
        "confidence": "high",
        "items": [
            {
                "name": "H-Milch 3,5%",
                "quantity": 1,
                "unit": "stk",
                "unit_price": 1.09,
                "total_price": 1.09,
                "vat_class": "B",
                "type": "product",
                "category": "Milchprodukte & Eier",
            }
        ],
    }
    data.update(overrides)
    return json.dumps(data)


def test_json_parser_reads_header_and_items() -> None:
    parsed = parse_receipt_json(_payload())
    assert parsed.store_name == "EDEKA"
    assert parsed.total_cents == 471
    assert parsed.purchased_at is not None
    assert parsed.purchased_at.date().isoformat() == "2026-03-04"
    assert parsed.items[0].unit_price_cents == 109
    assert parsed.items[0].category == "Milchprodukte & Eier"


def test_json_parser_tolerates_code_fences() -> None:
    parsed = parse_receipt_json(f"```json\n{_payload()}\n```")
    assert parsed.total_cents == 471


def test_json_parser_skips_unusable_items_but_keeps_good_ones() -> None:
    """Eine kaputte Zeile darf nicht 30 gute Positionen kosten."""
    raw = _payload(
        items=[
            {"name": "Gut", "total_price": 1.00, "type": "product"},
            {"name": "Ohne Preis", "type": "product"},
            {"total_price": 2.00, "type": "product"},
            "gar kein Objekt",
        ]
    )
    parsed = parse_receipt_json(raw)
    assert [i.name for i in parsed.items] == ["Gut"]


def test_json_parser_drops_category_on_deposit() -> None:
    raw = _payload(items=[{"name": "PFAND", "total_price": 0.25, "type": "deposit", "category": "Alkohol"}])
    assert parse_receipt_json(raw).items[0].category is None


def test_json_parser_defaults_unknown_type_to_product() -> None:
    raw = _payload(items=[{"name": "X", "total_price": 1.0, "type": "quatsch"}])
    assert parse_receipt_json(raw).items[0].kind == "product"


@pytest.mark.parametrize("raw", ["kein json", "[]", '{"store_name": "X"}'])
def test_json_parser_rejects_unusable_payloads(raw: str) -> None:
    with pytest.raises(ExtractionError):
        parse_receipt_json(raw)


# --- Konsistenzprüfung --------------------------------------------------------


def test_reconcile_flags_sum_mismatch() -> None:
    receipt = ParsedReceipt(
        total_cents=1000,
        confidence="high",
        items=[ParsedLineItem(name="A", total_price_cents=500)],
    )
    assert reconcile(receipt) == ("medium", True)


def test_reconcile_accepts_rounding_difference() -> None:
    receipt = ParsedReceipt(
        total_cents=1000,
        confidence="high",
        items=[ParsedLineItem(name="A", total_price_cents=999)],
    )
    assert reconcile(receipt) == ("high", False)


def test_reconcile_requires_review_without_items() -> None:
    assert reconcile(ParsedReceipt(total_cents=1000, confidence="high")) == ("high", True)


# --- Kategorie-Vorschlag ------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("H-MILCH 3,5%", "Milchprodukte & Eier"),
        ("GOUDA JUNG", "Käse"),
        ("BANANEN", "Obst"),
        ("TOMATEN RISPE", "Gemüse"),
        ("SPUELI ULTRA", "Haushalt & Reinigung"),
        ("Völlig unbekanntes Ding", None),
    ],
)
def test_guess_category(name: str, expected: str | None) -> None:
    assert guess_category(name) == expected
