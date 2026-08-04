"""Bon-Interpretation — rein und I/O-frei.

Zwei Wege, ein Ergebnistyp:

* `parse_receipt_text` — regelbasierter Parser für deutsche **eBon-PDFs**
  (REWE, Lidl, Kaufland …). Der Normalfall bei digitalen Belegen, und er
  braucht **kein Modell**.
* `parse_receipt_json` — liest die JSON-Antwort des Vision-LLM für Fotos und
  Scans.

Beträge werden hier zu Cent (ADR-003). Der Service verdrahtet das Ergebnis mit
Speicher, LLM und Datenbank — hier passiert nichts davon, damit alles ohne
Modell und ohne Datenbank testbar bleibt.
"""

from __future__ import annotations

import contextlib
import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from app.domain.money import (
    parse_amount,
    parse_de_amount,
    parse_de_quantity,
    parse_quantity,
    totals_match,
)

LINE_KINDS = ("product", "deposit", "discount")
CONFIDENCES = ("high", "medium", "low")

_FENCE = re.compile(r"^```(?:json)?|```$", re.MULTILINE)


class ExtractionError(ValueError):
    """Die Modellantwort ließ sich nicht in eine Bon-Struktur überführen."""


@dataclass
class ParsedLineItem:
    name: str
    total_price_cents: int
    quantity_milli: int | None = None
    unit: str | None = None
    unit_price_cents: int | None = None
    vat_class: str | None = None
    kind: str = "product"
    category: str | None = None


@dataclass
class ParsedReceipt:
    currency: str = "EUR"
    store_name: str | None = None
    purchased_at: datetime | None = None
    total_cents: int | None = None
    confidence: str = "medium"
    items: list[ParsedLineItem] = field(default_factory=list)

    @property
    def item_sum_cents(self) -> int:
        return sum(item.total_price_cents for item in self.items)


# --- Weg 1: JSON aus dem Vision-LLM ------------------------------------------


def _parse_when(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    with contextlib.suppress(ValueError):
        return datetime.fromisoformat(raw)
    with contextlib.suppress(ValueError):  # nur Datum → Mitternacht
        return datetime.combine(date.fromisoformat(raw), datetime.min.time())
    return None


def _strip_fences(raw: str) -> str:
    """Versehentliche ```json-Fences entfernen und das äußerste Objekt greifen."""
    text = _FENCE.sub("", raw).strip()
    start, end = text.find("{"), text.rfind("}")
    return text[start : end + 1] if start != -1 and end > start else text


def parse_receipt_json(raw: str) -> ParsedReceipt:
    """JSON des Modells in einen `ParsedReceipt` überführen.

    Wirft `ExtractionError`, wenn die Antwort kein JSON-Objekt mit `items` ist.
    Einzelne kaputte Positionen werden übersprungen statt den ganzen Bon zu
    verwerfen — ein fehlender Preis in Zeile 12 darf nicht 30 gute Positionen
    kosten.
    """
    try:
        data = json.loads(_strip_fences(raw))
    except json.JSONDecodeError as exc:
        raise ExtractionError(f"kein gültiges JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtractionError("JSON-Objekt erwartet")

    raw_items = data.get("items")
    if not isinstance(raw_items, list):
        raise ExtractionError("'items' muss eine Liste sein")

    confidence = data.get("confidence")
    receipt = ParsedReceipt(
        currency=str(data.get("currency") or "EUR").upper()[:8],
        store_name=str(data["store_name"]).strip() or None if data.get("store_name") else None,
        purchased_at=_parse_when(data.get("purchased_at")),
        total_cents=parse_amount(data.get("total")),
        confidence=confidence if confidence in CONFIDENCES else "medium",
    )

    for entry in raw_items:
        if not isinstance(entry, dict):
            continue
        total_price = parse_amount(entry.get("total_price"))
        name = entry.get("name")
        if total_price is None or not name:
            continue  # ohne Name oder Preis unbrauchbar
        kind = str(entry["type"]) if entry.get("type") in LINE_KINDS else "product"
        receipt.items.append(
            ParsedLineItem(
                name=str(name).strip(),
                total_price_cents=total_price,
                quantity_milli=parse_quantity(entry.get("quantity")),
                unit=str(entry["unit"]).strip() or None if entry.get("unit") else None,
                unit_price_cents=parse_amount(entry.get("unit_price")),
                vat_class=str(entry["vat_class"])[:4] if entry.get("vat_class") else None,
                kind=kind,
                # Pfand und Rabatt tragen laut Vertrag keine Kategorie.
                category=(
                    str(entry["category"])
                    if kind == "product" and entry.get("category")
                    else None
                ),
            )
        )
    return receipt


# --- Weg 2: Text-PDF (digitaler eBon) ----------------------------------------
# Viele Bon-PDFs sind *Text*-PDFs, keine Scans: ihr Inhalt ist extrahierbarer
# Text mit sehr regelmäßigem Layout. Den parsen wir direkt — solche Bons kosten
# damit kein Modell. Unbekannte Layouts liefern wenige oder keine Positionen und
# landen über den Summencheck in `needs_review`.

_AMOUNT = r"-?\d{1,3}(?:\.\d{3})*,\d{2}"
# Einfache Artikelzeile: "NAME <Lücke> 1,99 B" (MwSt-Buchstabe und "*" optional).
_ITEM_LINE = re.compile(
    rf"^(?P<name>.+?)\s{{2,}}(?P<amount>{_AMOUNT})\s*(?P<vat>[A-Za-z])?\s*\*?\s*$"
)
# Artikel mit Menge in derselben Zeile (Lidl): "NAME  0,29 x 6  1,74 B"
_ITEM_INLINE_QTY = re.compile(
    rf"^(?P<name>.+?)\s{{2,}}(?P<up>\d+,\d{{2}})\s*[x×]\s*(?P<qty>\d+(?:,\d+)?)\s+"
    rf"(?P<amount>{_AMOUNT})\s*(?P<vat>[A-Za-z])?\s*\*?\s*$"
)
# Mengen-Detailzeile unter dem Artikel: "2 Stk x 1,45" / "0,512 kg x 5,99 EUR/kg".
_QTY_COUNT = re.compile(
    r"^(?P<qty>\d+(?:,\d+)?)\s*(?P<unit>Stk|St)\.?\s*[x×]\s*(?P<price>\d+(?:,\d+)?)",
    re.IGNORECASE,
)
_QTY_WEIGHT = re.compile(
    r"^(?P<qty>\d+(?:,\d+)?)\s*(?P<unit>kg|g|l|ml)\s*[x×]\s*(?P<price>\d+(?:,\d+)?)",
    re.IGNORECASE,
)
# Summenzeile — Ketten formulieren unterschiedlich (REWE "SUMME", Lidl "zu
# zahlen"). Der ERSTE Treffer zählt, damit die MwSt-Aufstellung darunter (die
# ebenfalls "Summe" enthält) nicht in den Artikelbereich rutscht.
_TOTAL = re.compile(
    rf"^(?:zu\s+zahlen|summe|gesamtbetrag|gesamtsumme|gesamt)\b.*?(?P<amount>{_AMOUNT})\s*$",
    re.IGNORECASE,
)
_DEPOSIT_KEYWORDS = ("PFAND", "LEERG")
# Ketten am Textmarker erkennen: das Logo ist ein Bild, der Name steht oft nur
# im Kleingedruckten ("Lidl Plus", "www.lidl.de"). Marker sind spezifisch genug,
# um nicht die MwSt-Spalte zu treffen.
_KNOWN_STORES: list[tuple[str, tuple[str, ...]]] = [
    ("Lidl", ("LIDL PLUS", "WWW.LIDL", "LIDL.DE")),
    ("REWE", ("REWE MARKT", "WWW.REWE", "REWE.DE")),
    ("Kaufland", ("KAUFLAND",)),
    ("ALDI", ("ALDI SÜD", "ALDI NORD", "WWW.ALDI")),
    ("EDEKA", ("EDEKA ", "WWW.EDEKA")),
    ("PENNY", ("PENNY MARKT", "WWW.PENNY", "PENNY.DE")),
    ("Netto", ("NETTO MARKEN", "NETTO-ONLINE", "NETTO.DE")),
    ("Rossmann", ("ROSSMANN",)),
    ("dm", ("DM-DROGERIE", "WWW.DM.DE")),
]


def _spaced_letters(line: str) -> bool:
    """True für einen gesperrt gedruckten Kopf, z. B. REWEs "R E W E"."""
    tokens = line.split()
    return len(tokens) >= 2 and all(len(token) == 1 for token in tokens)


def _make_item(name: str, amount_cents: int, vat: str | None) -> ParsedLineItem:
    """Position bauen und über Schlüsselwort/Vorzeichen einordnen."""
    upper = name.upper()
    if any(keyword in upper for keyword in _DEPOSIT_KEYWORDS):
        kind = "deposit"
    elif amount_cents < 0:
        kind = "discount"
    else:
        kind = "product"
    return ParsedLineItem(
        name=name,
        total_price_cents=amount_cents,
        vat_class=vat.upper() if vat else None,
        kind=kind,
    )


def _find_store(text: str, lines: list[str]) -> str | None:
    upper = text.upper()
    for canonical, markers in _KNOWN_STORES:
        if any(marker in upper for marker in markers):
            return canonical
    for line in lines[:8]:
        stripped = line.strip()
        if len(stripped) >= 2 and any(c.isalpha() for c in stripped) and "EUR" not in stripped:
            if _spaced_letters(stripped):
                return "".join(stripped.split())
            return re.sub(r"\s{2,}", " ", stripped)
    return None


def _find_purchased_at(text: str) -> datetime | None:
    """Datum aus deutschem TT.MM.JJJJ (+ optionale Uhrzeit), sonst aus einem
    ISO-Datum — manche eBons tragen nur den ISO-Zeitstempel."""
    german = re.search(r"(\d{2}\.\d{2}\.\d{4})", text)
    if german is not None:
        try:
            when = datetime.strptime(german.group(1), "%d.%m.%Y")
        except ValueError:
            return None
        clock = re.search(r"(\d{2}):(\d{2})(?::(\d{2}))?", text)
        if clock is not None:
            when = when.replace(
                hour=int(clock.group(1)),
                minute=int(clock.group(2)),
                second=int(clock.group(3) or 0),
            )
        return when
    iso = re.search(r"(\d{4})-(\d{2})-(\d{2})", text)
    if iso is not None:
        with contextlib.suppress(ValueError):
            return datetime(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    return None


def parse_receipt_text(text: str) -> ParsedReceipt:
    """Text eines deutschen eBons in einen `ParsedReceipt` überführen.

    Regelbasiert, ohne Modell: Artikelzeilen tragen den Preis (mit
    MwSt-Buchstaben), eine mögliche Folgezeile die Menge, und eine
    `SUMME`-Zeile die Endsumme. Nur Zeilen **oberhalb** der Summe gelten als
    Artikel, damit Zahlart und Fußzeile draußen bleiben. Ein Fehlparse fällt
    oben über den Summencheck auf.
    """
    lines = [line.rstrip() for line in text.splitlines()]
    receipt = ParsedReceipt(store_name=_find_store(text, lines))

    # Endsumme finden — und damit die Grenze, unter der keine Artikel mehr stehen.
    total_idx: int | None = None
    for i, line in enumerate(lines):
        match = _TOTAL.match(line.strip())
        if match:
            receipt.total_cents = parse_de_amount(match.group("amount"))
            total_idx = i
            break

    current: ParsedLineItem | None = None
    for line in lines[:total_idx] if total_idx is not None else lines:
        stripped = line.strip()
        if not stripped:
            continue

        qty = _QTY_COUNT.match(stripped) or _QTY_WEIGHT.match(stripped)
        if qty is not None:  # Mengenzeile — gehört zum Artikel darüber
            if current is not None:
                current.quantity_milli = parse_de_quantity(qty.group("qty"))
                current.unit = qty.group("unit").lower()
                current.unit_price_cents = parse_de_amount(qty.group("price"))
            continue

        inline = _ITEM_INLINE_QTY.match(stripped)
        if inline is not None:  # "Stückpreis x Anzahl  Gesamt" in einer Zeile
            amount = parse_de_amount(inline.group("amount"))
            name = inline.group("name").strip()
            if amount is not None and any(c.isalpha() for c in name):
                current = _make_item(name, amount, inline.group("vat"))
                current.quantity_milli = parse_de_quantity(inline.group("qty"))
                current.unit = "stk"
                current.unit_price_cents = parse_de_amount(inline.group("up"))
                receipt.items.append(current)
            continue

        item = _ITEM_LINE.match(stripped)
        if item is None:
            continue
        amount = parse_de_amount(item.group("amount"))
        name = item.group("name").strip()
        if amount is None or not any(c.isalpha() for c in name):
            continue  # Kopf-/Adressrauschen ohne echten Produktnamen
        current = _make_item(name, amount, item.group("vat"))
        receipt.items.append(current)

    receipt.purchased_at = _find_purchased_at("\n".join(lines))
    # Nur mit Positionen *und* Endsumme ist der Bon gegenrechenbar; sonst
    # erzwingt "low" die manuelle Prüfung.
    receipt.confidence = "high" if (receipt.items and receipt.total_cents is not None) else "low"
    return receipt


# --- Kategorie-Vorschlag ------------------------------------------------------
# Schlüsselwort → Kategoriename aus dem Seed (erster Treffer gewinnt, geordnet
# von spezifisch nach allgemein). Damit kommen textgeparste eBons — die keine
# Kategorie mitbringen — vorsortiert an. Kein Treffer heißt keine Kategorie:
# lieber keine als eine falsche.
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
                           "NÜSSE", "CHOCO", "WAFFEL", "EISCREME")),
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
    """Bester Rateversuch: Kategoriename für einen deutschen Artikelnamen."""
    haystack = f" {name.upper()} "
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(keyword in haystack for keyword in keywords):
            return category
    return None


def reconcile(receipt: ParsedReceipt) -> tuple[str, bool]:
    """`(confidence, needs_review)` nach dem Plausibilitätscheck.

    Summiert alle Positionen (Rabatte und Leergut-Rückgaben negativ) und
    vergleicht mit der gedruckten Endsumme. Weicht sie über die Toleranz ab —
    oder meldete das Modell bereits niedrige Zuversicht, oder gibt es keine
    Positionen — muss ein Mensch draufschauen.
    """
    confidence = receipt.confidence
    needs_review = confidence == "low" or not receipt.items

    if (
        receipt.total_cents is not None
        and receipt.items
        and not totals_match(receipt.item_sum_cents, receipt.total_cents)
    ):
        needs_review = True
        if confidence == "high":
            confidence = "medium"

    return confidence, needs_review
