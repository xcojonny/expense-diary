import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPkMixin

USER_STATUSES = ("pending", "active", "disabled")
MAGIC_LINK_PURPOSES = ("login", "invite")


class User(Base, UUIDPkMixin, TimestampMixin):
    """An account. No password: login is via magic link or OIDC only."""

    __tablename__ = "users"
    __table_args__ = (
        sa.CheckConstraint("status IN ('pending','active','disabled')", name="status"),
    )

    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    display_name: Mapped[str]
    locale: Mapped[str] = mapped_column(default="de", server_default="de")
    is_instance_admin: Mapped[bool] = mapped_column(default=False, server_default=sa.false())
    status: Mapped[str] = mapped_column(default="pending", server_default="pending")
    last_login_at: Mapped[datetime | None]


class MagicLinkToken(Base, UUIDPkMixin, TimestampMixin):
    """Single-use, short-lived login token. Only the hash is stored; the raw
    token travels in the emailed link."""

    __tablename__ = "magic_link_tokens"

    email: Mapped[str] = mapped_column(CITEXT)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]


class RefreshToken(Base, UUIDPkMixin, TimestampMixin):
    """Rotating refresh token (httpOnly cookie). Stored hashed; rotated on every
    refresh and revoked on logout."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]


class OidcIdentity(Base, UUIDPkMixin, TimestampMixin):
    """Link between a local user and an external OIDC subject (Authelia)."""

    __tablename__ = "oidc_identities"
    __table_args__ = (sa.UniqueConstraint("issuer", "subject", name="issuer_subject"),)

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    issuer: Mapped[str]
    subject: Mapped[str]
