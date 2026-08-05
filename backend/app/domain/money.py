"""Geld und Mengen — die einzige Stelle, an der Beträge interpretiert werden.

Rein und I/O-frei. Beträge sind **ganzzahlige Cent**, Mengen **Tausendstel**
(ADR-003): JSON überträgt Ganzzahlen exakt, und `parseFloat` an der UI-Grenze
kann es gar nicht mehr geben.
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

CENTS_PER_EURO = 100
MILLI = 1000

# Toleranz beim Abgleich Positionssumme ↔ gedruckte Endsumme: der größere Wert
# aus 2 Cent und 1 % schluckt Rundung, ohne echte Fehler zu verstecken.
_ABS_TOLERANCE_CENTS = 2
_REL_TOLERANCE_BP = 100  # 1 % in Basispunkten

_CURRENCY_NOISE = str.maketrans({"€": None, "$": None, " ": None, " ": None})


def _to_decimal(value: object, *, german: bool) -> Decimal | None:
    """Wandelt Zahl oder Text in ein Decimal.

    `german=True`: Punkt ist Tausendertrennzeichen, Komma Dezimaltrennzeichen
    ("1.234,56"). `german=False`: das **zuletzt** auftretende Trennzeichen ist
    das Dezimaltrennzeichen — damit sind sowohl "1234.56" (wie im Prompt
    gefordert) als auch versehentliches "1.234,56" korrekt lesbar.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, float):
        return Decimal(str(value))
    if not isinstance(value, str):
        return None

    text = value.strip().translate(_CURRENCY_NOISE)
    if not text:
        return None

    if german:
        text = text.replace(".", "").replace(",", ".")
    else:
        last_dot, last_comma = text.rfind("."), text.rfind(",")
        if last_dot >= 0 and last_comma >= 0:
            if last_comma > last_dot:  # "1.234,56"
                text = text.replace(".", "").replace(",", ".")
            else:  # "1,234.56"
                text = text.replace(",", "")
        elif last_comma >= 0:  # "3,49"
            text = text.replace(",", ".")

    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _decimal_to_cents(value: Decimal) -> int:
    return int((value * CENTS_PER_EURO).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def parse_de_amount(text: str) -> int | None:
    """Deutsch formatierten Betrag nach Cent parsen: "1.234,56" → 123456."""
    value = _to_decimal(text, german=True)
    return None if value is None else _decimal_to_cents(value)


def parse_amount(value: object) -> int | None:
    """Betrag aus LLM-JSON nach Cent parsen: 3.49 → 349, "3,49" → 349."""
    parsed = _to_decimal(value, german=False)
    return None if parsed is None else _decimal_to_cents(parsed)


def parse_de_quantity(text: str) -> int | None:
    """Deutsch formatierte Menge nach Tausendstel: "0,432" → 432."""
    value = _to_decimal(text, german=True)
    return None if value is None else int((value * MILLI).quantize(Decimal(1), ROUND_HALF_UP))


def parse_quantity(value: object) -> int | None:
    """Menge aus LLM-JSON nach Tausendstel: 0.432 → 432."""
    parsed = _to_decimal(value, german=False)
    return None if parsed is None else int((parsed * MILLI).quantize(Decimal(1), ROUND_HALF_UP))


def average_cents(values: Iterable[int]) -> int | None:
    """Arithmetisches Mittel in Cent, kaufmännisch gerundet."""
    items = list(values)
    if not items:
        return None
    return int((Decimal(sum(items)) / len(items)).quantize(Decimal(1), ROUND_HALF_UP))


def share_bp(part: int, whole: int) -> int | None:
    """Anteil in Basispunkten (1/10.000). `None`, wenn das Ganze null ist.

    Basispunkte statt Fließkommazahl, damit der Anteil dieselbe Exaktheit
    behält wie die Beträge, aus denen er entsteht (ADR-003).
    """
    if whole == 0:
        return None
    return int((Decimal(part) * 10_000 / whole).quantize(Decimal(1), ROUND_HALF_UP))


def totals_match(item_sum_cents: int, printed_total_cents: int) -> bool:
    """Prüft, ob Positionssumme und gedruckte Endsumme plausibel zueinander passen."""
    tolerance = max(
        _ABS_TOLERANCE_CENTS,
        abs(printed_total_cents) * _REL_TOLERANCE_BP // 10_000,
    )
    return abs(item_sum_cents - printed_total_cents) <= tolerance


def unit_price_from_total(total_cents: int, quantity_milli: int | None) -> int | None:
    """Stückpreis aus Gesamtpreis und Menge — für Positionen, die keinen
    eigenen Stückpreis mitbringen. `None` bei fehlender oder Null-Menge."""
    if not quantity_milli:
        return None
    return int(
        (Decimal(total_cents) * MILLI / quantity_milli).quantize(Decimal(1), ROUND_HALF_UP)
    )
