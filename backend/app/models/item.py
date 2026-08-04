from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.line_item import LineItem


class Item(Base, TimestampMixin):
    """Produkt-Stammdatum — der Anker für den Preisverlauf.

    `normalized_name` ist eindeutig und kommt aus `domain.normalize`. Weil dort
    schon kleingeschrieben wird, genügt eine gewöhnliche Textspalte (kein
    `CITEXT` nötig — ADR-001).
    """

    __tablename__ = "items"

    id: Mapped[int] = mapped_column(primary_key=True)
    normalized_name: Mapped[str] = mapped_column(
        sa.String(240), nullable=False, unique=True, index=True
    )
    display_name: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    category: Mapped[Category | None] = relationship(back_populates="items")
    line_items: Mapped[list[LineItem]] = relationship(back_populates="item")
