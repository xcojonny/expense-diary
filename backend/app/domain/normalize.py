"""Product-name normalization — pure, I/O-free domain logic.

This is the key that lets the same product compare across receipts and over
time: "H-Milch 3,5%", "H MILCH 3.5" and "h.milch 3,5 %" all collapse to one
``normalized_name``. Deliberately simple (folding + tidy-up); a smarter
matcher can layer on top later without changing the contract.
"""

import re
import unicodedata

# German umlauts / ß expand the way shoppers and receipts spell them out.
_UMLAUT_MAP = str.maketrans(
    {
        "ä": "ae",
        "ö": "oe",
        "ü": "ue",
        "ß": "ss",
    }
)

_DIGIT_COMMA = re.compile(r"(?<=\d),(?=\d)")  # decimal comma between digits → dot
_NON_ALNUM = re.compile(r"[^a-z0-9]+")  # collapse everything else to a space
_MULTISPACE = re.compile(r"\s+")


def normalize_name(raw: str) -> str:
    """Return a stable, comparable key for a product name.

    Steps: lowercase → expand umlauts/ß → strip accents → unify decimal comma
    to a dot → drop all other punctuation → collapse whitespace. Returns an
    empty string for input that has no alphanumerics.
    """
    if not raw:
        return ""

    text = raw.lower().translate(_UMLAUT_MAP)
    # Strip remaining diacritics (é → e) without touching ASCII letters.
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))

    text = _DIGIT_COMMA.sub(".", text)
    text = _NON_ALNUM.sub(" ", text)
    text = _MULTISPACE.sub(" ", text).strip()
    return text
