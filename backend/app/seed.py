"""Kategorien-Seed — idempotent, läuft bei jedem Start.

Die Top-Level-Namen sind exakt die, die der Extraktions-Prompt vergeben darf;
extrahierte Positionen treffen damit direkt auf eine existierende Kategorie.
`is_food` ist ein Feld (ADR-007), also wird es hier gesetzt statt im Code
geraten.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category

# (Elternteil | None, Name, Sortierung, is_food)
CATEGORY_TREE: list[tuple[str | None, str, int, bool]] = [
    (None, "Obst & Gemüse", 10, True),
    (None, "Milchprodukte & Eier", 20, True),
    (None, "Fleisch & Wurst", 30, True),
    (None, "Fisch", 40, True),
    (None, "Brot & Backwaren", 50, True),
    (None, "Kaffee, Tee & Kakao", 60, True),
    (None, "Getränke (alkoholfrei)", 70, True),
    (None, "Alkohol", 80, True),
    (None, "Süßwaren & Snacks", 90, True),
    (None, "Grundnahrungsmittel", 100, True),
    (None, "Öle, Gewürze & Kochzutaten", 110, True),
    (None, "Fertiggerichte", 120, True),
    (None, "Haushalt & Reinigung", 130, False),
    (None, "Drogerie & Körperpflege", 140, False),
    (None, "Tierbedarf", 150, False),
    (None, "Baby & Kind", 160, False),
    (None, "Sonstiges", 999, False),
    # Ein paar Unterkategorien, damit die Hierarchie echt ist. Der Prompt
    # vergibt die Top-Level-Namen; feiner einordnen kann man von Hand.
    ("Obst & Gemüse", "Obst", 11, True),
    ("Obst & Gemüse", "Gemüse", 12, True),
    ("Milchprodukte & Eier", "Käse", 21, True),
    ("Milchprodukte & Eier", "Joghurt & Quark", 22, True),
]


async def seed_categories(session: AsyncSession) -> int:
    """Fehlende Kategorien anlegen; Anzahl der neuen zurückgeben.

    Idempotent und nicht-destruktiv: vorhandene Kategorien werden nicht
    angefasst, damit eine Umbenennung durch den Nutzer beim nächsten Start
    nicht zurückgesetzt wird.
    """
    existing = {
        (parent_id, name.casefold()): cid
        for name, parent_id, cid in (
            await session.execute(sa.select(Category.name, Category.parent_id, Category.id))
        ).all()
    }
    created = 0

    for parent_name, name, sort_order, is_food in CATEGORY_TREE:
        parent_id = existing.get((None, parent_name.casefold())) if parent_name else None
        if parent_name is not None and parent_id is None:
            continue  # Elternteil wurde gelöscht — Unterkategorie überspringen
        if (parent_id, name.casefold()) in existing:
            continue

        category = Category(
            name=name, parent_id=parent_id, sort_order=sort_order, is_food=is_food
        )
        session.add(category)
        await session.flush()
        existing[(parent_id, name.casefold())] = category.id
        created += 1

    return created
