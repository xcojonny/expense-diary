from functools import lru_cache
from pathlib import Path

_DIR = Path(__file__).resolve().parent


@lru_cache
def load_extraction_prompt(locale: str = "de") -> str:
    """Load the editable receipt-extraction prompt for the given locale,
    falling back to German. Cached — edits need a reload to take effect."""
    for candidate in (f"receipt_extraction.{locale}.txt", "receipt_extraction.de.txt"):
        path = _DIR / candidate
        if path.exists():
            return path.read_text(encoding="utf-8")
    raise FileNotFoundError("no receipt extraction prompt found")
