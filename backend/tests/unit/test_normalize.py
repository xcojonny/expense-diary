from app.domain.normalize import normalize_name


def test_empty_input() -> None:
    assert normalize_name("") == ""
    assert normalize_name("   ") == ""
    assert normalize_name("%%%") == ""


def test_lowercases_and_trims() -> None:
    assert normalize_name("  REWE Bio Milch  ") == "rewe bio milch"


def test_umlauts_and_eszett_are_expanded() -> None:
    assert normalize_name("Gemüse") == "gemuese"
    assert normalize_name("Frischkäse") == "frischkaese"
    assert normalize_name("Weiße Soße") == "weisse sosse"


def test_accents_are_stripped() -> None:
    assert normalize_name("Café Crème") == "cafe creme"


def test_the_canonical_milk_example_collapses() -> None:
    # The requirement: "H-Milch 3,5%" and "H MILCH 3.5" must be one key.
    assert normalize_name("H-Milch 3,5%") == normalize_name("H MILCH 3.5")


def test_punctuation_and_multispace_collapse() -> None:
    assert normalize_name("H-Milch 3,5%") == "h milch 3 5"
    assert normalize_name("Joghurt,   Natur!!") == "joghurt natur"


def test_decimal_comma_and_dot_are_equivalent() -> None:
    assert normalize_name("Gouda 2,50") == normalize_name("Gouda 2.50")
