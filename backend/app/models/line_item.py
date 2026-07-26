import enum
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.receipt import Receipt


class LineType(enum.StrEnum):
    product = "product"
    deposit = "deposit"  # Pfand / Leergut (return = negative total_price)
    discount = "discount"  # Rabatt / Coupon (negative total_price)


_LINE_TYPE_VALUES = ", ".join(f"'{t.value}'" for t in LineType)


class LineItem(Base, UUIDPkMixin, TimestampMixin):
    """A single position on a receipt. ``normalized_name`` is derived from
    ``name`` via domain.normalize and links the line to its Item master record
    for trend analysis; deposit/discount lines carry no category."""

    __tablename__ = "line_items"
    __table_args__ = (
        sa.CheckConstraint(f"line_type IN ({_LINE_TYPE_VALUES})", name="line_type"),
    )

    receipt_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("receipts.id", ondelete="CASCADE")
    )
    item_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("items.id", ondelete="SET NULL")
    )
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("categories.id", ondelete="SET NULL")
    )

    name: Mapped[str]  # as printed on the receipt
    normalized_name: Mapped[str | None] = mapped_column(CITEXT, index=True)
    quantity: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 3))  # count OR weight
    unit: Mapped[str | None]  # stk | kg | g | l | ...
    unit_price: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 2))
    total_price: Mapped[Decimal] = mapped_column(sa.Numeric(10, 2))  # negative for discounts
    vat_class: Mapped[str | None]  # A | B | ... when printed
    line_type: Mapped[LineType] = mapped_column(
        sa.Text, default=LineType.product, server_default=LineType.product.value
    )

    receipt: Mapped["Receipt"] = relationship(back_populates="line_items")
