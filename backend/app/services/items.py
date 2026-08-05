"""Positionen auf Produkt-Stammdaten abbilden — der Trend-Anker.

Diese Funktion ist die **einzige** Stelle, die `normalized_name` und `item_id`
setzt. Extraktion und manuelle Korrektur laufen beide hierdurch, damit eine
korrigierte Position denselben Preisverlauf füttert wie eine extrahierte. Der
Client setzt diese Felder nie.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.normalize import normalize_name
from app.models import Item, LineItem


async def get_or_create_item(
    session: AsyncSession, *, household_id: int, display_name: str, category_id: int | None
) -> Item | None:
    """Stammdatum zum normalisierten Namen holen oder anlegen — **pro Haushalt**.

    `None`, wenn der Name nichts Vergleichbares übrig lässt (z. B. „***").
    """
    normalized = normalize_name(display_name)
    if not normalized:
        return None

    existing = (
        await session.execute(
            sa.select(Item).where(
                Item.household_id == household_id, Item.normalized_name == normalized
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        # Eine Kategorie am Stammdatum, die noch fehlt, nachtragen — so lernt
        # der Artikel aus der ersten Position, die eine Kategorie mitbringt.
        if existing.category_id is None and category_id is not None:
            existing.category_id = category_id
        return existing

    item = Item(
        household_id=household_id,
        normalized_name=normalized,
        display_name=display_name.strip(),
        category_id=category_id,
    )
    session.add(item)
    await session.flush()
    return item


async def apply_product_mapping(
    session: AsyncSession, line_item: LineItem, *, household_id: int
) -> None:
    """`normalized_name` und `item_id` an einer Position setzen.

    Nur Produktpositionen bekommen ein Stammdatum: Pfand und Rabatt sind
    bon-lokal und würden den Artikelkatalog mit „PFAND 0,25" zumüllen.
    """
    if line_item.kind != "product":
        line_item.normalized_name = ""
        line_item.item_id = None
        return

    line_item.normalized_name = normalize_name(line_item.name)
    item = await get_or_create_item(
        session,
        household_id=household_id,
        display_name=line_item.name,
        category_id=line_item.category_id,
    )
    line_item.item_id = item.id if item is not None else None
    # Kategorie vom Stammdatum erben, wenn die Position keine hat — der Nutzer
    # kategorisiert einen Artikel damit genau einmal.
    if line_item.category_id is None and item is not None:
        line_item.category_id = item.category_id
