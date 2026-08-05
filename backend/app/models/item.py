from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.household import Household
    from app.models.line_item import LineItem


class Item(Base, TimestampMixin):
    """Produkt-Stammdatum — der Anker für den Preisverlauf.

    `normalized_name` kommt aus `domain.normalize` und ist **pro Haushalt**
    eindeutig. Weil dort schon kleingeschrieben wird, genügt eine gewöhnliche
    Textspalte (kein `CITEXT` nötig — ADR-001).
    """

    __tablename__ = "items"
    __table_args__ = (
        # Pro Haushalt eindeutig, nicht global: jeder Haushalt hat seinen eigenen
        # Artikelkatalog und damit seinen eigenen Preisverlauf.
        sa.UniqueConstraint("household_id", "normalized_name", name="uq_items_household_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    normalized_name: Mapped[str] = mapped_column(sa.String(240), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    category_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    household: Mapped[Household] = relationship(back_populates="items")
    category: Mapped[Category | None] = relationship(back_populates="items")
    line_items: Mapped[list[LineItem]] = relationship(back_populates="item")
