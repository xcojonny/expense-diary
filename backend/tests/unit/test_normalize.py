from __future__ import annotations

import pytest

from app.domain.normalize import normalize_name


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("H-Milch 3,5%", "h milch 3 5"),
        ("H MILCH 3.5", "h milch 3 5"),
        ("h.milch 3,5 %", "h milch 3 5"),
        ("Müsli", "muesli"),
        ("MUESLI", "muesli"),
        ("Crème fraîche", "creme fraiche"),
        ("Straße", "strasse"),
        ("  Doppel   Leerzeichen  ", "doppel leerzeichen"),
        ("***", ""),
        ("", ""),
    ],
)
def test_normalize_name(raw: str, expected: str) -> None:
    assert normalize_name(raw) == expected


def test_spelling_variants_collapse_to_one_key() -> None:
    """Der eigentliche Zweck: ohne das gibt es keinen Preisverlauf."""
    variants = ["H-Milch 3,5%", "H MILCH 3.5", "h.milch 3,5 %", "H_Milch_3,5%"]
    assert len({normalize_name(v) for v in variants}) == 1
