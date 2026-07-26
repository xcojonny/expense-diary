"""Shared Item-mapping logic: turn a line's name into a group-scoped Item
(the trend anchor). Used by both the extraction pipeline and manual editing so
they stay consistent — a hand-corrected name re-maps exactly like an extracted
one.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.normalize import normalize_name
from app.models import Item, LineItem, LineType


async def resolve_item(
    session: AsyncSession,
    *,
    group_id: uuid.UUID,
    normalized: str,
    display_name: str,
    category_id: uuid.UUID | None,
    cache: dict[str, Item] | None = None,
) -> Item:
    """Get or create the Item for (group, normalized_name). ``cache`` avoids
    duplicate inserts when mapping several lines of one receipt in a batch."""
    if cache is not None and normalized in cache:
        return cache[normalized]
    item = (
        await session.execute(
            select(Item).where(Item.group_id == group_id, Item.normalized_name == normalized)
        )
    ).scalar_one_or_none()
    if item is None:
        item = Item(
            group_id=group_id,
            normalized_name=normalized,
            display_name=display_name,
            category_id=category_id,
        )
        session.add(item)
        await session.flush()  # need item.id for the line FK
    if cache is not None:
        cache[normalized] = item
    return item


async def apply_product_mapping(
    session: AsyncSession,
    line: LineItem,
    *,
    group_id: uuid.UUID,
    category_id: uuid.UUID | None,
    cache: dict[str, Item] | None = None,
) -> None:
    """Set (or clear) ``normalized_name`` and ``item_id`` on a line to match its
    current name and type. Only real products anchor to an Item; deposit/discount
    lines are receipt-local."""
    if line.line_type == LineType.product:
        normalized = normalize_name(line.name)
        if normalized:
            line.normalized_name = normalized
            item = await resolve_item(
                session,
                group_id=group_id,
                normalized=normalized,
                display_name=line.name,
                category_id=category_id,
                cache=cache,
            )
            line.item_id = item.id
            if category_id is not None and item.category_id is None:
                item.category_id = category_id
            return
    line.normalized_name = None
    line.item_id = None
