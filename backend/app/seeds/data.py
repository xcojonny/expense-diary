"""Default category tree (German). Top level mirrors the categories the
extraction prompt is allowed to assign; a couple of sub-categories seed the
hierarchy so parent_id is actually exercised. Names are what the LLM returns,
so extracted line items map onto these directly.
"""

# (parent_name | None, name, sort_order)
CATEGORY_TREE: list[tuple[str | None, str, int]] = [
    (None, "Obst & Gemüse", 10),
    (None, "Milchprodukte & Eier", 20),
    (None, "Fleisch & Wurst", 30),
    (None, "Fisch", 40),
    (None, "Brot & Backwaren", 50),
    (None, "Kaffee, Tee & Kakao", 60),
    (None, "Getränke (alkoholfrei)", 70),
    (None, "Alkohol", 80),
    (None, "Süßwaren & Snacks", 90),
    (None, "Grundnahrungsmittel", 100),
    (None, "Öle, Gewürze & Kochzutaten", 110),
    (None, "Fertiggerichte", 120),
    (None, "Haushalt & Reinigung", 130),
    (None, "Drogerie & Körperpflege", 140),
    (None, "Tierbedarf", 150),
    (None, "Baby & Kind", 160),
    (None, "Sonstiges", 999),
    # A few sub-categories to make the hierarchy real. The extraction prompt
    # assigns the top-level names; users can re-file line items into these.
    ("Milchprodukte & Eier", "Käse", 21),
    ("Milchprodukte & Eier", "Joghurt & Quark", 22),
    ("Obst & Gemüse", "Obst", 11),
    ("Obst & Gemüse", "Gemüse", 12),
]
