"""Produktnamen-Normalisierung — rein und I/O-frei.

Der Schlüssel, der denselben Artikel über Bons und über Zeit vergleichbar
macht: „H-Milch 3,5 %“, „H MILCH 3.5“ und „h.milch 3,5%“ fallen auf denselben
`normalized_name`. Bewusst einfach (Falten + Aufräumen); ein klügerer Matcher
kann später aufsetzen, ohne den Vertrag zu ändern.

Weil hier schon kleingeschrieben wird, braucht die Datenbank keinen
case-insensitiven Spaltentyp (`CITEXT`) — ein Grund, warum SQLite reicht
(ADR-001).
"""

from __future__ import annotations

import re
import unicodedata

# Umlaute und ß so ausschreiben, wie Kunden und Bons sie schreiben.
_UMLAUT_MAP = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

_DIGIT_COMMA = re.compile(r"(?<=\d),(?=\d)")  # Dezimalkomma zwischen Ziffern → Punkt
_NON_ALNUM = re.compile(r"[^a-z0-9]+")  # alles andere zu Leerzeichen
_MULTISPACE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Stabiler, vergleichbarer Schlüssel für einen Produktnamen.

    Schritte: kleinschreiben → Umlaute/ß ausschreiben → Akzente entfernen →
    Dezimalkomma zu Punkt → übrige Zeichen verwerfen → Leerzeichen glätten.
    Ergibt einen leeren String, wenn keine Alphanumerik übrig bleibt.
    """
    if not raw:
        return ""

    text = raw.lower().translate(_UMLAUT_MAP)
    # Restliche Diakritika entfernen (é → e), ohne ASCII anzutasten.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    text = _DIGIT_COMMA.sub(".", text)
    text = _NON_ALNUM.sub(" ", text)
    return _MULTISPACE.sub(" ", text).strip()
