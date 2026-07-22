import uuid

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class Item(Base, UUIDPkMixin, TimestampMixin):
    """Product master record — the anchor for cross-receipt price trends.

    Line items map onto an Item by their ``normalized_name`` so that the same
    product bought on different receipts over time compares as one thing
    ("H-Milch 3,5%" and "H MILCH 3.5" collapse to the same Item).
    """

    __tablename__ = "items"

    # The trend key. CITEXT keeps lookups case-insensitive on top of the
    # explicit normalization applied before writing.
    normalized_name: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str | None]  # prettiest name seen on a receipt
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("categories.id", ondelete="SET NULL")
    )
