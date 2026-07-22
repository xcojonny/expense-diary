from decimal import Decimal

import pytest

from app.domain.extraction import (
    ExtractionError,
    ParsedLineItem,
    ParsedReceipt,
    parse_receipt_json,
    reconcile_confidence,
)

FULL = """
{
  "store_name": "REWE",
  "purchased_at": "2026-07-01",
  "currency": "EUR",
  "total": 1.04,
  "confidence": "high",
  "items": [
    {"name": "Bio Milch", "quantity": 1, "unit": "stk", "unit_price": 1.29, "total_price": 1.29, "vat_class": "B", "type": "product", "category": "Milchprodukte & Eier"},
    {"name": "PFAND", "quantity": 1, "unit": "stk", "total_price": 0.25, "type": "deposit", "category": null},
    {"name": "RABATT", "total_price": -0.50, "type": "discount", "category": null}
  ]
}
"""


def test_parses_full_receipt() -> None:
    r = parse_receipt_json(FULL)
    assert r.store_name == "REWE"
    assert r.currency == "EUR"
    assert r.total == Decimal("1.04")
    assert r.purchased_at is not None and r.purchased_at.year == 2026
    assert len(r.items) == 3
    milk, pfand, rabatt = r.items
    assert milk.line_type == "product" and milk.category == "Milchprodukte & Eier"
    assert milk.unit_price == Decimal("1.29")
    assert pfand.line_type == "deposit" and pfand.category is None
    assert rabatt.line_type == "discount" and rabatt.total_price == Decimal("-0.50")


def test_strips_markdown_code_fences() -> None:
    fenced = '```json\n{"currency": "EUR", "total": null, "items": []}\n```'
    r = parse_receipt_json(fenced)
    assert r.currency == "EUR"
    assert r.items == []


def test_german_decimal_comma_is_tolerated() -> None:
    r = parse_receipt_json('{"currency":"EUR","total":"2,50","items":[{"name":"X","total_price":"2,50"}]}')
    assert r.total == Decimal("2.50")
    assert r.items[0].total_price == Decimal("2.50")


def test_items_without_price_or_name_are_skipped() -> None:
    r = parse_receipt_json(
        '{"items":[{"name":"ok","total_price":1.0},{"name":"no price"},{"total_price":2.0}]}'
    )
    assert [i.name for i in r.items] == ["ok"]


def test_invalid_payloads_raise() -> None:
    with pytest.raises(ExtractionError):
        parse_receipt_json("not json")
    with pytest.raises(ExtractionError):
        parse_receipt_json("[1, 2, 3]")  # not an object
    with pytest.raises(ExtractionError):
        parse_receipt_json('{"no": "items key"}')


def _receipt(total: str | None, confidence: str, *totals: str) -> ParsedReceipt:
    return ParsedReceipt(
        total=Decimal(total) if total is not None else None,
        confidence=confidence,
        items=[ParsedLineItem(name=f"i{n}", total_price=Decimal(t)) for n, t in enumerate(totals)],
    )


def test_reconcile_matches_total() -> None:
    conf, needs_review = reconcile_confidence(_receipt("1.04", "high", "1.29", "0.25", "-0.50"))
    assert conf == "high"
    assert needs_review is False


def test_reconcile_flags_mismatch_and_caps_confidence() -> None:
    conf, needs_review = reconcile_confidence(_receipt("10.00", "high", "1.29"))
    assert needs_review is True
    assert conf == "medium"  # capped from high


def test_reconcile_low_confidence_needs_review() -> None:
    _conf, needs_review = reconcile_confidence(_receipt("1.29", "low", "1.29"))
    assert needs_review is True


def test_reconcile_no_items_needs_review() -> None:
    _conf, needs_review = reconcile_confidence(_receipt(None, "high"))
    assert needs_review is True
