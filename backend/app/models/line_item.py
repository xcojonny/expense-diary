from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.category import Category
    from app.models.item import Item
    from app.models.receipt import Receipt

LINE_KINDS = ("product", "deposit", "discount")


class LineItem(Base, TimestampMixin):
    """Eine Position auf dem Bon.

    `normalized_name` und `item_id` setzt **immer** der Server (über
    `services/items.py`), nie der Client — nur so landet eine manuell
    korrigierte Position am selben Trend-Anker wie eine extrahierte.
    """

    __tablename__ = "line_items"
    __table_args__ = (
        sa.CheckConstraint("kind IN ('product','deposit','discount')", name="ck_line_items_kind"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("items.id", ondelete="SET NULL"), nullable=True, index=True
    )
    category_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    position: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    name: Mapped[str] = mapped_column(sa.String(240), nullable=False)
    normalized_name: Mapped[str] = mapped_column(
        sa.String(240), default="", nullable=False, index=True
    )

    quantity_milli: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    unit: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    unit_price_cents: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    total_price_cents: Mapped[int] = mapped_column(sa.Integer, nullable=False)

    vat_class: Mapped[str | None] = mapped_column(sa.String(4), nullable=True)
    kind: Mapped[str] = mapped_column(sa.String(12), default="product", nullable=False, index=True)

    receipt: Mapped[Receipt] = relationship(back_populates="line_items")
    item: Mapped[Item | None] = relationship(back_populates="line_items")
    category: Mapped[Category | None] = relationship(back_populates="line_items")
