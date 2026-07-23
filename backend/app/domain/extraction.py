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


# -- Text (digital eBon) parsing ---------------------------------------------
# Many receipt PDFs (REWE, Kaufland, Lidl … digital eBons) are *text* PDFs, not
# scans — their content is extractable text with a very regular layout. We parse
# that directly, so these receipts are recognized without any vision LLM. Unknown
# layouts yield few/no items and get routed to needs_review by the sum check.

_TEXT_AMOUNT = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
# An item line: "NAME <gap> 1,99 B" (optional VAT letter, optional trailing "*").
_ITEM_LINE = re.compile(
    rf"^(?P<name>.+?)\s{{2,}}(?P<amount>{_TEXT_AMOUNT})\s*(?P<vat>[A-Za-z])?\s*\*?\s*$"
)
# A quantity detail line under the item: "2 Stk x 1,45" or "0,512 kg x 5,99 EUR/kg".
_QTY_COUNT = re.compile(
    r"^(?P<qty>\d+(?:,\d+)?)\s*(?P<unit>Stk|St)\.?\s*[x\u00d7]\s*(?P<price>\d+(?:,\d+)?)",
    re.IGNORECASE,
)
_QTY_WEIGHT = re.compile(
    r"^(?P<qty>\d+(?:,\d+)?)\s*(?P<unit>kg|g|l|ml)\s*[x\u00d7]\s*(?P<price>\d+(?:,\d+)?)",
    re.IGNORECASE,
)
_SUMME = re.compile(rf"^SUMME\b.*?(?P<amount>{_TEXT_AMOUNT})\s*$", re.IGNORECASE)
_DEPOSIT_KEYWORDS = ("PFAND", "LEERG")  # LEERG. / LEERGUT → deposit line


def _de_amount(text: str) -> Decimal | None:
    """Parse a German-formatted amount ("1.234,56", "-0,60") to Decimal."""
    try:
        return Decimal(text.strip().replace(".", "").replace(",", "."))
    except (InvalidOperation, ValueError):
        return None


def _spaced_letters(line: str) -> bool:
    """True for a header printed letter-spaced, e.g. REWE's "R E W E"."""
    tokens = line.split()
    return len(tokens) >= 2 and all(len(token) == 1 for token in tokens)


def parse_receipt_text(text: str) -> ParsedReceipt:
    """Parse a German digital-receipt (eBon) *text* dump into a ParsedReceipt.

    Rule-based and LLM-free: item lines carry the price (with the VAT-class
    letter), an optional following line the quantity/unit, and a ``SUMME`` line
    the total. Only lines above ``SUMME`` are treated as items, so payment and
    footer lines are ignored. The upstream sum check catches a misparse.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    receipt = ParsedReceipt()

    # Store name: first meaningful header line (REWE prints it spaced: "R E W E").
    for line in lines[:8]:
        stripped = line.strip()
        if len(stripped) >= 2 and any(c.isalpha() for c in stripped) and "EUR" not in stripped:
            receipt.store_name = (
                "".join(stripped.split())
                if _spaced_letters(stripped)
                else re.sub(r"\s{2,}", " ", stripped)
            )
            break

    # Total + the cutoff below which we stop treating lines as items.
    total_idx: int | None = None
    for i, line in enumerate(lines):
        match = _SUMME.match(line.strip())
        if match:
            receipt.total = _de_amount(match.group("amount"))
            total_idx = i
            break

    current: ParsedLineItem | None = None
    for line in lines[:total_idx] if total_idx is not None else lines:
        stripped = line.strip()
        if not stripped:
            continue
        qty = _QTY_COUNT.match(stripped) or _QTY_WEIGHT.match(stripped)
        if qty is not None:  # a quantity detail line — attach to the item above
            if current is not None:
                current.quantity = _de_amount(qty.group("qty"))
                current.unit = qty.group("unit")
                current.unit_price = _de_amount(qty.group("price"))
            continue
        item = _ITEM_LINE.match(stripped)
        if item is None:
            continue
        name = item.group("name").strip()
        amount = _de_amount(item.group("amount"))
        if amount is None or not any(c.isalpha() for c in name):
            continue  # header/address noise without a real product name
        upper = name.upper()
        if any(keyword in upper for keyword in _DEPOSIT_KEYWORDS):
            line_type = "deposit"
        elif amount < 0:
            line_type = "discount"
        else:
            line_type = "product"
        vat = item.group("vat")
        current = ParsedLineItem(
            name=name,
            total_price=amount,
            vat_class=vat.upper() if vat else None,
            line_type=line_type,
        )
        receipt.items.append(current)

    joined = "\n".join(lines)
    date_match = re.search(r"(\d{2}\.\d{2}\.\d{4})", joined)
    time_match = re.search(r"(\d{2}:\d{2}(?::\d{2})?)", joined)
    if date_match is not None:
        try:
            when = datetime.strptime(date_match.group(1), "%d.%m.%Y")
            if time_match is not None:
                parts = [int(p) for p in time_match.group(1).split(":")]
                when = when.replace(
                    hour=parts[0], minute=parts[1], second=parts[2] if len(parts) > 2 else 0
                )
            receipt.purchased_at = when
        except ValueError:
            pass

    # Only auto-complete when we have items *and* a total to reconcile against;
    # otherwise force manual review (confidence "low").
    receipt.confidence = "high" if (receipt.items and receipt.total is not None) else "low"
    return receipt


# Keyword → seeded category name (first match wins, ordered specific→general).
# Names must exist in the seed tree so the service can map them to an id. This
# is a best-effort guess for German grocery items so text-parsed eBons arrive
# pre-categorized; the user can always re-file. No match → no category (better
# none than wrong).
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("Käse", ("KAESE", "KÄSE", "GOUDA", "FRISCHK", "CAMEMBERT", "MOZZAREL", "EDAMER",
              "GERAMONT", "PARMESAN", "FETA", "BUTTERKAESE")),
    ("Joghurt & Quark", ("JOGHURT", "JOGURT", "QUARK", "SKYR")),
    ("Milchprodukte & Eier", ("MILCH", "SAHNE", "BUTTER", "EIER", "MASCARPONE",
                              "H-MILCH", "HMILCH", "MARGARINE")),
    ("Obst", ("APFEL", "BANANE", "MANGO", "HEIDELB", "BEERE", "BIRNE", "TRAUBE",
              "ORANGE", "ZITRONE", "KIWI", "PFIRSICH", "ERDBEER", "MELONE", "AVOCADO",
              "ANANAS", "MANDARIN", "NEKTARINE", "PFLAUME")),
    ("Gemüse", ("KAROTTE", "MOEHRE", "MÖHRE", "TOMATE", "PAPRIKA", "FENCHEL",
                "CHAMPIGNON", "PILZ", "GURKE", "ZWIEBEL", "KARTOFFEL", "SALAT",
                "BROKKOLI", "ZUCCHINI", "LAUCH", "KOHL", "SELLERIE", "SPINAT",
                "ROSMARI", "BASILIK", "PETERSIL", "KRAEUTER", "KRÄUTER", "INGWER",
                "KNOBLAUCH", "AUBERGINE", "RADIESCHEN", "SPARGEL")),
    ("Fleisch & Wurst", ("HACK", "WURST", "SCHINKEN", "SALAMI", "HAEHNCHEN",
                         "HÄHNCHEN", "PUTE", "RIND", "SCHWEIN", "SPECK", "BRATWURST",
                         "FLEISCH", "GEFLUEGEL", "GEFLÜGEL", "METT", "SCHNITZEL")),
    ("Fisch", ("LACHS", "THUNFISCH", "GARNELE", "FORELLE", "HERING", "FISCH",
               "MAKRELE", "SCAMPI")),
    ("Brot & Backwaren", ("BROT", "BROETCHEN", "BRÖTCHEN", "BAGUETTE", "TOAST",
                          "CROISSANT", "GEBAECK", "GEBÄCK", "SEMMEL", "ZWIEBACK",
                          "BREZEL")),
    ("Kaffee, Tee & Kakao", ("KAFFEE", "ESPRESSO", "KAKAO", "TEE", "CAPPUCCINO")),
    ("Getränke (alkoholfrei)", ("WASSER", "COLA", "SAFT", "LIMO", "SCHORLE", "EISTEE",
                                "MINERALW", "SPRUDEL", "BRAUSE", "SPEZI")),
    ("Alkohol", ("BIER", "WEIN", "SEKT", "PROSECCO", "VODKA", "WHISKY", "LIKOER",
                 "LIKÖR", "APEROL", " GIN ", " RUM ")),
    ("Süßwaren & Snacks", ("SCHOKO", "CHIPS", "KEKS", "GUMMI", "BONBON", "RIEGEL",
                           "SNACK", "POPCORN", "CRACKER", "PRALINE", "NUSS", "NUESSE",
                           "NÜSSE", "CHOCO", "WAFFEL")),
    ("Grundnahrungsmittel", ("MEHL", "ZUCKER", "REIS", "NUDEL", "PASTA", "HAFERFL",
                             "LINSEN", "BOHNEN", "KICH", "MUESLI", "MÜSLI", "HAFER",
                             "GRIESS", "GRIEß", "COUSCOUS", "POLENTA")),
    ("Öle, Gewürze & Kochzutaten", ("OLIVEN", "ESSIG", " SALZ", "PFEFFER", "GEWUERZ",
                                    "GEWÜRZ", "SENF", "KETCHUP", "SOSSE", "SAUCE",
                                    "BRUEHE", "BRÜHE", "OEL ", "ÖL ")),
    ("Fertiggerichte", ("PIZZA", "FERTIG", "TIEFKUEHL", "LASAGNE", "MAULTASCHEN")),
    ("Haushalt & Reinigung", ("SPUELI", "SPÜLI", "WASCH", "REINIG", "PUTZ",
                              "MUELLBEUTEL", "KLOPAPIER", "TOILETTENP", "ALUFOLIE",
                              "FROSCH", "KUECHENROLLE")),
    ("Drogerie & Körperpflege", ("SHAMPOO", "DUSCH", "ZAHNP", "SEIFE", " DEO", "CREME",
                                 "RASIER", "TAMPON", "BINDEN", "WATTE", "LOTION")),
    ("Tierbedarf", ("HUNDE", "KATZEN", "TIERF", "KATZENFUTTER", "HUNDEFUTTER")),
    ("Baby & Kind", ("WINDEL", " BABY", "BREI")),
]


def guess_category(name: str) -> str | None:
    """Best-effort keyword → seeded-category name for a German grocery item.
    Used as a fallback so text-parsed eBons (which carry no category) arrive
    pre-categorized. Returns None when nothing matches."""
    haystack = f" {name.upper()} "
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return None


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
