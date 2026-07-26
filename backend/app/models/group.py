import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin

GROUP_ROLES = ("admin", "member")


class Group(Base, UUIDPkMixin, TimestampMixin):
    """A household — the tenancy boundary that owns receipts and item history.

    Members join via ``GroupMember`` (role admin/member); an admin can invite
    others. A user's active group is resolved per request in ``api/deps``.
    """

    __tablename__ = "groups"

    name: Mapped[str]
    created_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )

    members: Mapped[list["GroupMember"]] = relationship(
        cascade="all, delete-orphan", passive_deletes=True
    )


class GroupMember(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "group_members"
    __table_args__ = (
        sa.UniqueConstraint("group_id", "user_id", name="group_user"),
        sa.CheckConstraint("role IN ('admin','member')", name="role"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    role: Mapped[str] = mapped_column(default="member", server_default="member")


class GroupInvitation(Base, UUIDPkMixin, TimestampMixin):
    """Pending invitation to join a group. The raw token travels in the emailed
    link; only its hash is stored. Accepting it creates/activates the user and
    their membership."""

    __tablename__ = "group_invitations"

    group_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(CITEXT)
    role: Mapped[str] = mapped_column(default="member", server_default="member")
    token_hash: Mapped[str] = mapped_column(unique=True)
    invited_by: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL")
    )
    expires_at: Mapped[datetime]
    accepted_at: Mapped[datetime | None]
