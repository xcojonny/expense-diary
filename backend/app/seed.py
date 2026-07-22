"""Idempotent master-data seeding — run via ``python -m app.seed``.

Seeds the category tree. Safe to re-run: existing categories (matched by
parent + name) are left untouched.
"""

import asyncio

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.models import Category
from app.seeds.data import CATEGORY_TREE


async def seed_categories(session: AsyncSession) -> int:
    """Insert missing categories. Returns the number of rows created."""
    # Two passes so a child can resolve its parent regardless of list order.
    existing = (await session.execute(select(Category))).scalars().all()
    by_name: dict[tuple[str | None, str], Category] = {
        (c.parent.name if c.parent else None, c.name): c for c in existing
    }

    created = 0
    # Pass 1: top-level rows.
    for parent_name, name, sort_order in CATEGORY_TREE:
        if parent_name is not None:
            continue
        if (None, name) in by_name:
            continue
        cat = Category(name=name, sort_order=sort_order)
        session.add(cat)
        by_name[(None, name)] = cat
        created += 1
    await session.flush()

    # Pass 2: children, now that parents exist.
    for parent_name, name, sort_order in CATEGORY_TREE:
        if parent_name is None:
            continue
        if (parent_name, name) in by_name:
            continue
        parent = by_name.get((None, parent_name))
        if parent is None:
            raise ValueError(f"Seed error: parent category '{parent_name}' not found")
        session.add(Category(name=name, sort_order=sort_order, parent_id=parent.id))
        created += 1

    await session.commit()
    return created


async def main() -> None:
    async with get_sessionmaker()() as session:
        created = await seed_categories(session)
    print(f"seed: {created} categories created")


if __name__ == "__main__":
    asyncio.run(main())
