"""Rule-based parsing of German digital-receipt (eBon) text PDFs — the REWE
sample that motivated the feature (a text PDF, not a scan)."""

from datetime import datetime
from decimal import Decimal

from app.domain.extraction import guess_category, parse_receipt_text, reconcile_confidence

# Verbatim text as extracted from a real REWE eBon PDF (pypdf), spacing and all.
REWE = """\
               R E W E
           Siebenmorgen 40
      51427 Berg.Gladb.(Refrath)
          Tel. 02204-962437
         UID Nr.: DE812706034
                                   EUR
GOUDA SCHEIBEN                   1,99 B
GERAMONT SCHB.                   2,49 B
BIO KOER FRISCHK                 2,90 B
             2 Stk x    1,45
KAROTTE BIO                      2,99 B
TOMATE MINIR.                    3,49 B
PAPRIKA ROT                      3,07 B
         0,512 kg x   5,99 EUR/kg
FENCHEL                          2,03 B
         0,508 kg x   3,99 EUR/kg
CHAMPIGNONS                      2,29 B
MANGO                            3,59 B
KULTURHEIDELB.                   3,49 B
NATURALS ROSMARI                 4,58 B
             2 Stk x    2,29
BIO KICH.ERB.CHI                 3,58 B
             2 Stk x    1,79
LEERG. MW V. ST                 -0,60 A *
             4 Stk x    0,15
LEERGUT EINWEG                  -2,25 A *
             9 Stk x    0,25
 --------------------------------------
 SUMME                   EUR     33,64
 ======================================
 Geg. EC-Cash            EUR     33,64
Datum:                        13.06.2026
Uhrzeit:                    16:26:58 Uhr
"""


def test_parses_rewe_ebon_and_reconciles() -> None:
    receipt = parse_receipt_text(REWE)

    assert receipt.store_name == "REWE"  # "R E W E" → collapsed
    assert receipt.total == Decimal("33.64")
    assert receipt.purchased_at == datetime(2026, 6, 13, 16, 26, 58)

    # 12 products + 2 deposit returns.
    assert len(receipt.items) == 14
    assert sum(1 for i in receipt.items if i.line_type == "deposit") == 2

    gouda = receipt.items[0]
    assert gouda.name == "GOUDA SCHEIBEN"
    assert gouda.total_price == Decimal("1.99")
    assert gouda.vat_class == "B"
    assert gouda.line_type == "product"

    # Quantity detail line attaches to the item above it.
    frischk = next(i for i in receipt.items if i.name == "BIO KOER FRISCHK")
    assert frischk.quantity == Decimal("2")
    assert frischk.unit == "Stk"
    assert frischk.unit_price == Decimal("1.45")

    # Weight-priced item.
    paprika = next(i for i in receipt.items if i.name == "PAPRIKA ROT")
    assert paprika.quantity == Decimal("0.512")
    assert paprika.unit == "kg"
    assert paprika.unit_price == Decimal("5.99")

    # Deposit return: negative, classified as deposit, not a product.
    leergut = next(i for i in receipt.items if i.name == "LEERGUT EINWEG")
    assert leergut.total_price == Decimal("-2.25")
    assert leergut.line_type == "deposit"

    # Line sum equals the printed total → recognized (done, not needs_review).
    item_sum = sum((i.total_price for i in receipt.items), Decimal(0))
    assert item_sum == Decimal("33.64")
    confidence, needs_review = reconcile_confidence(receipt)
    assert confidence == "high"
    assert needs_review is False

    # Payment/footer lines below SUMME are not mistaken for items.
    assert all("EC-Cash" not in i.name for i in receipt.items)


# Lidl eBon: different layout — total is "zu zahlen", quantities are inline
# ("0,29 x 6 1,74"), per-item "Lidl Plus Rabatt" discounts, VAT table below the
# total. Transcribed to sum exactly to the payable total.
LIDL = """\
Abt-Hafner-Str. 14
87629 Füssen
                                   EUR
Tomate Cherrys.                    8,83 A
   1,108 kg x 7,97   EUR/kg
   Lidl Plus Rabatt               -2,96
Gurken Feld lo.                    0,83 A
   0,334 kg x 2,49   EUR/kg
   Lidl Plus Rabatt               -0,17
Bio Paprika rot                    2,29 A
   Lidl Plus Rabatt               -0,40
Bioland Eier OKT 6er   3,19 x  2   6,38 A
Mineralwasser          0,29 x  6   1,74 B
Pfand 0,25 EM          0,25 x  6   1,50 B
Cashew-Cranberry-MIx               1,99 A
 --------------------------------------
 zu zahlen                        20,03
 Karte                            20,03

 MWST%   MWST +   Netto = Brutto
 A  7 %   1,00   10,00   11,00
 B 19 %   1,00    8,00    9,03
 Summe    2,00   18,00   20,03
 Gesamter Preisvorteil  3,53 EUR gespart
2026-07-21T15:34:49.000Z
"""


def test_parses_lidl_ebon() -> None:
    receipt = parse_receipt_text(LIDL)

    assert receipt.store_name == "Lidl"  # from "Lidl Plus" marker, not the address
    assert receipt.total == Decimal("20.03")  # "zu zahlen", not the VAT-table "Summe"
    assert receipt.purchased_at is not None
    assert receipt.purchased_at.date().isoformat() == "2026-07-21"

    names = [i.name for i in receipt.items]
    # The VAT-breakdown rows below "zu zahlen" must NOT become items.
    assert not any(n.startswith("A ") or n.startswith("B ") for n in names)

    # Inline quantity: "0,29 x 6" → qty 6 at 0,29.
    water = next(i for i in receipt.items if i.name == "Mineralwasser")
    assert water.quantity == Decimal("6")
    assert water.unit_price == Decimal("0.29")
    assert water.total_price == Decimal("1.74")

    # Weight sub-line attaches to the item above it.
    tomato = next(i for i in receipt.items if i.name == "Tomate Cherrys.")
    assert tomato.unit == "kg"
    assert tomato.unit_price == Decimal("7.97")

    # Deposit + discounts classified correctly.
    assert next(i for i in receipt.items if "Pfand" in i.name).line_type == "deposit"
    discounts = [i for i in receipt.items if i.name == "Lidl Plus Rabatt"]
    assert len(discounts) == 3
    assert all(d.line_type == "discount" and d.total_price < 0 for d in discounts)

    # Line items reconcile to the payable total → recognized.
    item_sum = sum((i.total_price for i in receipt.items), Decimal(0))
    assert item_sum == Decimal("20.03")
    confidence, needs_review = reconcile_confidence(receipt)
    assert confidence == "high"
    assert needs_review is False


def test_guess_category_for_common_german_items() -> None:
    assert guess_category("GOUDA SCHEIBEN") == "Käse"
    assert guess_category("BIO KOER FRISCHK") == "Käse"
    assert guess_category("KAROTTE BIO") == "Gemüse"
    assert guess_category("CHAMPIGNONS") == "Gemüse"
    assert guess_category("MANGO") == "Obst"
    assert guess_category("KULTURHEIDELB.") == "Obst"
    assert guess_category("NATURALS ROSMARI") == "Gemüse"
    assert guess_category("BIO KICH.ERB.CHI") == "Grundnahrungsmittel"
    # Unknown / non-product → no guess (better none than wrong).
    assert guess_category("LEERGUT EINWEG") is None
    assert guess_category("XYZ VOELLIG UNBEKANNT") is None


def test_unknown_text_yields_no_items() -> None:
    receipt = parse_receipt_text("just some prose without any receipt structure")
    assert receipt.items == []
    # No items → forced to manual review upstream.
    _confidence, needs_review = reconcile_confidence(receipt)
    assert needs_review is True
