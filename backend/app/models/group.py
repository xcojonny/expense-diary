from sqlalchemy.orm import Mapped

from app.db.base import Base, TimestampMixin, UUIDPkMixin


class Group(Base, UUIDPkMixin, TimestampMixin):
    """A household — the tenancy boundary that owns receipts and item history.

    Deliberately minimal for now: full multi-group support (auth, memberships,
    roles) lands later. Baking ``group_id`` into the owned tables and resolving
    a bootstrapped default group today means that later step is auth + a
    membership table, not a schema migration + data backfill.
    """

    __tablename__ = "groups"

    name: Mapped[str]
