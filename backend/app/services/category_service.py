"""Category management (phase 5). Categories are shared master data (not
group-owned). Guards duplicate names within a parent and parent cycles, which
the raw self-referencing FK cannot enforce.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Category
from app.schemas.category import CategoryCreate, CategoryUpdate


class CategoryError(ValueError):
    """Invalid category operation (duplicate name / bad parent / cycle)."""


async def _get(session: AsyncSession, category_id: uuid.UUID) -> Category | None:
    return await session.get(Category, category_id)


async def _duplicate_exists(
    session: AsyncSession, name: str, parent_id: uuid.UUID | None, exclude: uuid.UUID | None
) -> bool:
    stmt = select(Category.id).where(Category.name == name)
    stmt = stmt.where(Category.parent_id == parent_id) if parent_id else stmt.where(
        Category.parent_id.is_(None)
    )
    if exclude is not None:
        stmt = stmt.where(Category.id != exclude)
    return (await session.execute(stmt)).first() is not None


async def _would_cycle(
    session: AsyncSession, category_id: uuid.UUID, new_parent_id: uuid.UUID
) -> bool:
    """True if making ``new_parent_id`` the parent of ``category_id`` creates a
    loop — i.e. category_id is new_parent_id or one of its ancestors."""
    cursor: uuid.UUID | None = new_parent_id
    while cursor is not None:
        if cursor == category_id:
            return True
        parent = await _get(session, cursor)
        cursor = parent.parent_id if parent else None
    return False


async def _validate_parent(
    session: AsyncSession, parent_id: uuid.UUID | None, *, of: uuid.UUID | None
) -> None:
    if parent_id is None:
        return
    if of is not None and parent_id == of:
        raise CategoryError("Eine Kategorie kann nicht ihr eigenes Elternteil sein.")
    if await _get(session, parent_id) is None:
        raise CategoryError("Übergeordnete Kategorie nicht gefunden.")
    if of is not None and await _would_cycle(session, of, parent_id):
        raise CategoryError("Diese Verschachtelung würde einen Zyklus erzeugen.")


async def create_category(session: AsyncSession, data: CategoryCreate) -> Category:
    name = data.name.strip()
    await _validate_parent(session, data.parent_id, of=None)
    if await _duplicate_exists(session, name, data.parent_id, exclude=None):
        raise CategoryError("Es gibt bereits eine Kategorie mit diesem Namen an dieser Stelle.")
    category = Category(name=name, parent_id=data.parent_id, sort_order=data.sort_order)
    session.add(category)
    await session.commit()
    await session.refresh(category)
    return category


async def update_category(
    session: AsyncSession, category: Category, data: CategoryUpdate
) -> Category:
    fields = data.model_dump(exclude_unset=True)
    new_name = fields["name"].strip() if "name" in fields else category.name
    new_parent = fields.get("parent_id", category.parent_id)

    if "parent_id" in fields:
        await _validate_parent(session, new_parent, of=category.id)
    if ("name" in fields or "parent_id" in fields) and await _duplicate_exists(
        session, new_name, new_parent, exclude=category.id
    ):
        raise CategoryError("Es gibt bereits eine Kategorie mit diesem Namen an dieser Stelle.")

    category.name = new_name
    category.parent_id = new_parent
    if "sort_order" in fields:
        category.sort_order = fields["sort_order"]
    await session.commit()
    await session.refresh(category)
    return category


async def delete_category(session: AsyncSession, category: Category) -> None:
    """Delete a category. Its children become top-level and any line-item/item
    references are cleared (both via FK ON DELETE SET NULL)."""
    await session.delete(category)
    await session.commit()
