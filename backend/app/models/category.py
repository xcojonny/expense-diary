import uuid

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class Category(Base, UUIDPkMixin, TimestampMixin):
    """Spending category, self-referencing for a hierarchy
    (e.g. Lebensmittel > Milchprodukte). Top-level rows have parent_id = NULL.
    """

    __tablename__ = "categories"
    __table_args__ = (
        # A name is unique within its parent, so "Sonstiges" can exist under
        # several parents but not twice under the same one. NULL parents collide
        # under Postgres' default NULLS-DISTINCT, so seeding guards top-level
        # duplicates in code (see seeds/data.py).
        sa.UniqueConstraint("parent_id", "name", name="parent_name"),
    )

    name: Mapped[str]
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("categories.id", ondelete="SET NULL")
    )
    sort_order: Mapped[int] = mapped_column(default=0, server_default="0")

    children: Mapped[list["Category"]] = relationship(
        back_populates="parent", cascade="all", passive_deletes=True
    )
    parent: Mapped["Category | None"] = relationship(
        back_populates="children", remote_side="Category.id"
    )
