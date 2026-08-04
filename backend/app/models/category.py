from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.line_item import LineItem


class Category(Base, TimestampMixin):
    """Hierarchische Kategorie.

    `is_food` ist bewusst ein **Feld** und keine Namensliste im Code (ADR-007):
    Kategorien sind umbenennbar, und eine Umbenennung darf die Kennzahl
    „Anteil am Lebensmittelbudget" nicht stillschweigend verfälschen.
    """

    __tablename__ = "categories"
    __table_args__ = (
        # SQLite behandelt NULLs als verschieden — für Top-Level-Kategorien
        # (parent_id IS NULL) greift das hier also nicht. Den Fall prüft
        # zusätzlich `services/categories.py`.
        sa.UniqueConstraint("parent_id", "name", name="uq_categories_parent_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)
    parent_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=100, nullable=False)
    is_food: Mapped[bool] = mapped_column(sa.Boolean, default=True, nullable=False)

    parent: Mapped[Category | None] = relationship(
        remote_side=lambda: [Category.id], back_populates="children"
    )
    children: Mapped[list[Category]] = relationship(
        back_populates="parent", cascade="save-update"
    )
    line_items: Mapped[list[LineItem]] = relationship(back_populates="category")
    items: Mapped[list[Item]] = relationship(back_populates="category")
