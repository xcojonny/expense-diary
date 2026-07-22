"""Pure parsing + consistency logic for receipt extraction — no I/O.

The vision LLM returns text; everything that *interprets* it lives here so it
is unit-testable without a model or a database. The service layer only wires
this to storage, the LLM adapter, and the DB.
"""

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

VALID_LINE_TYPES = ("product", "deposit", "discount")
VALID_CONFIDENCE = ("high", "medium", "low")

# Tolerance when reconciling the item sum against the printed total: the larger
# of 2 cents or 1 % of the total absorbs rounding without hiding real errors.
_ABS_TOLERANCE = Decimal("0.02")
_REL_TOLERANCE = Decimal("0.01")

_FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)


class ExtractionError(ValueError):
    """The model output could not be parsed into a receipt structure."""


@dataclass
class ParsedLineItem:
    name: str
    total_price: Decimal
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    vat_class: str | None = None
    line_type: str = "product"
    category: str | None = None


@dataclass
class ParsedReceipt:
    currency: str = "EUR"
    store_name: str | None = None
    purchased_at: datetime | None = None
    total: Decimal | None = None
    confidence: str = "medium"
    items: list[ParsedLineItem] = field(default_factory=list)


def _to_decimal(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        # Accept "3,49" defensively even though the prompt asks for a dot.
        text = str(value).strip().replace(",", ".")
        return Decimal(text) if text else None
    except (InvalidOperation, ValueError):
        return None


def _parse_when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        pass
    try:  # date-only → midnight
        return datetime.combine(date.fromisoformat(raw), datetime.min.time())
    except ValueError:
        return None


def _strip_fences(raw: str) -> str:
    """Remove accidental ```json code fences and grab the outermost object."""
    text = _FENCE.sub("", raw).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


def parse_receipt_json(raw: str) -> ParsedReceipt:
    """Parse the model's JSON into a ParsedReceipt, coercing defensively.

    Raises ExtractionError if the payload is not a JSON object. Individual
    malformed items are skipped rather than failing the whole receipt.
    """
    try:
        data = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"invalid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtractionError("expected a JSON object")

    confidence = data.get("confidence")
    receipt = ParsedReceipt(
        currency=str(data.get("currency") or "EUR").upper()[:8],
        store_name=(str(data["store_name"]) if data.get("store_name") else None),
        purchased_at=_parse_when(data.get("purchased_at")),
        total=_to_decimal(data.get("total")),
        confidence=confidence if confidence in VALID_CONFIDENCE else "medium",
    )

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ExtractionError("'items' must be a list")

    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        total_price = _to_decimal(entry.get("total_price"))
        name = entry.get("name")
        if total_price is None or not name:
            continue  # a line without a price or name is unusable
        line_type = str(entry["type"]) if entry.get("type") in VALID_LINE_TYPES else "product"
        # deposit/discount carry no category by contract
        category = None
        if line_type == "product" and entry.get("category"):
            category = str(entry["category"])
        receipt.items.append(
            ParsedLineItem(
                name=str(name),
                total_price=total_price,
                quantity=_to_decimal(entry.get("quantity")),
                unit=(str(entry["unit"]) if entry.get("unit") else None),
                unit_price=_to_decimal(entry.get("unit_price")),
                vat_class=(str(entry["vat_class"]) if entry.get("vat_class") else None),
                line_type=line_type,
                category=category,
            )
        )
    return receipt


def reconcile_confidence(receipt: ParsedReceipt) -> tuple[str, bool]:
    """Return (confidence, needs_review) after a plausibility check.

    Sums all line totals (discounts negative, deposit returns negative) and
    compares to the printed total. A mismatch beyond tolerance — or a model
    that already reported low confidence, or a receipt with no items — forces
    manual review and caps confidence at "medium".
    """
    confidence = receipt.confidence
    needs_review = confidence == "low" or not receipt.items

    if receipt.total is not None and receipt.items:
        item_sum = sum((i.total_price for i in receipt.items), Decimal(0))
        tolerance = max(_ABS_TOLERANCE, abs(receipt.total) * _REL_TOLERANCE)
        if abs(item_sum - receipt.total) > tolerance:
            needs_review = True
            if confidence == "high":
                confidence = "medium"

    return confidence, needs_review
