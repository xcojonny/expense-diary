"""Kategorienverwaltung.

Drei Regeln, die die Datenbank allein nicht durchsetzt:

* **Doppelte Namen** unter demselben Elternteil sind verboten — der
  Unique-Index greift für Top-Level nicht, weil SQLite NULLs als verschieden
  behandelt.
* **Zyklen** beim Umhängen sind verboten: eine Kategorie darf nicht Nachfahre
  ihrer selbst werden.
* **Löschen kaskadiert keine Daten:** Unterkategorien werden zu Top-Level,
  Positions- und Artikelverweise auf `NULL`. Eine gelöschte Kategorie darf
  niemals Ausgaben mitnehmen.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category


class CategoryError(ValueError):
    """Fachlicher Konflikt (Duplikat, Zyklus, unbekanntes Elternteil)."""


async def list_all(session: AsyncSession) -> list[Category]:
    return list(
        (
            await session.execute(
                sa.select(Category).order_by(Category.sort_order, Category.name)
            )
        )
        .scalars()
        .all()
    )


async def _assert_name_free(
    session: AsyncSession, *, name: str, parent_id: int | None, exclude_id: int | None = None
) -> None:
    query = sa.select(Category.id).where(
        sa.func.lower(Category.name) == name.strip().lower(),
        Category.parent_id.is_(None) if parent_id is None else Category.parent_id == parent_id,
    )
    if exclude_id is not None:
        query = query.where(Category.id != exclude_id)
    if (await session.execute(query)).first() is not None:
        raise CategoryError(f"„{name}“ existiert an dieser Stelle schon.")


async def _assert_no_cycle(session: AsyncSession, *, category_id: int, parent_id: int) -> None:
    if category_id == parent_id:
        raise CategoryError("Eine Kategorie kann nicht ihr eigenes Elternteil sein.")
    # Vom neuen Elternteil nach oben laufen: tauchen wir selbst auf, wäre es ein Zyklus.
    current: int | None = parent_id
    seen: set[int] = set()
    while current is not None and current not in seen:
        seen.add(current)
        if current == category_id:
            raise CategoryError("Das würde die Kategorie unter sich selbst hängen.")
        current = (
            await session.execute(sa.select(Category.parent_id).where(Category.id == current))
        ).scalar_one_or_none()


async def create(
    session: AsyncSession,
    *,
    name: str,
    parent_id: int | None = None,
    sort_order: int = 100,
    is_food: bool | None = None,
) -> Category:
    name = name.strip()
    if not name:
        raise CategoryError("Der Name darf nicht leer sein.")

    parent: Category | None = None
    if parent_id is not None:
        parent = await session.get(Category, parent_id)
        if parent is None:
            raise CategoryError("Übergeordnete Kategorie existiert nicht.")
    await _assert_name_free(session, name=name, parent_id=parent_id)

    category = Category(
        name=name,
        parent_id=parent_id,
        sort_order=sort_order,
        # Unterkategorie erbt das Lebensmittel-Flag als Vorschlag (ADR-007).
        is_food=is_food if is_food is not None else (parent.is_food if parent else True),
    )
    session.add(category)
    await session.flush()
    return category


async def update(
    session: AsyncSession,
    category: Category,
    *,
    name: str | None = None,
    parent_id: int | None = None,
    clear_parent: bool = False,
    sort_order: int | None = None,
    is_food: bool | None = None,
) -> Category:
    if clear_parent:
        target_parent = None
    else:
        target_parent = parent_id if parent_id is not None else category.parent_id

    if parent_id is not None and not clear_parent:
        if await session.get(Category, parent_id) is None:
            raise CategoryError("Übergeordnete Kategorie existiert nicht.")
        await _assert_no_cycle(session, category_id=category.id, parent_id=parent_id)

    if name is not None or parent_id is not None or clear_parent:
        await _assert_name_free(
            session,
            name=name if name is not None else category.name,
            parent_id=target_parent,
            exclude_id=category.id,
        )

    if name is not None:
        stripped = name.strip()
        if not stripped:
            raise CategoryError("Der Name darf nicht leer sein.")
        category.name = stripped
    if clear_parent:
        category.parent_id = None
    elif parent_id is not None:
        category.parent_id = parent_id
    if sort_order is not None:
        category.sort_order = sort_order
    if is_food is not None:
        category.is_food = is_food

    await session.flush()
    return category


async def delete(session: AsyncSession, category: Category) -> None:
    """Kategorie entfernen, ohne Daten mitzunehmen (FKs sind `SET NULL`)."""
    await session.delete(category)
    await session.flush()
