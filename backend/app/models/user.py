import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column
from uuid6 import uuid7

from app.db.base import Base, TimestampMixin, UUIDPkMixin

USER_STATUSES = ("pending", "active", "disabled")


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
    email_verified_at: Mapped[datetime | None]
    last_login_at: Mapped[datetime | None]


class MagicLinkToken(Base, UUIDPkMixin, TimestampMixin):
    """Single-use, short-lived login token. Only the hash is stored; the raw
    token travels in the emailed link. Browser-bound: the link starts a session
    only in the browser that requested it (matching ``requester_hash``);
    elsewhere it yields a pairing code instead."""

    __tablename__ = "magic_link_tokens"

    email: Mapped[str] = mapped_column(CITEXT)
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE")
    )
    token_hash: Mapped[str] = mapped_column(unique=True)
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None]
    request_ip: Mapped[str | None]
    # SHA-256 of the requesting browser's cookie secret. Opening the link in a
    # different browser then shows a pairing code instead of a session.
    requester_hash: Mapped[str | None] = mapped_column(index=True)
    code_attempts: Mapped[int] = mapped_column(default=0, server_default="0")
    opened_at: Mapped[datetime | None]  # first cross-browser open — drives the login poll


class RefreshToken(Base, UUIDPkMixin, TimestampMixin):
    """Rotating refresh token (httpOnly cookie). Stored hashed; rotated on every
    refresh. Rotation family: replaying an already-rotated token revokes the
    whole family (theft defense)."""

    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    token_hash: Mapped[str] = mapped_column(unique=True)
    family_id: Mapped[uuid.UUID] = mapped_column(default=uuid7)
    expires_at: Mapped[datetime]
    revoked_at: Mapped[datetime | None]
    last_used_at: Mapped[datetime | None]
    user_agent: Mapped[str | None]
    ip: Mapped[str | None]


class OidcIdentity(Base, UUIDPkMixin, TimestampMixin):
    """Link between a local user and an external OIDC subject (Authelia)."""

    __tablename__ = "oidc_identities"
    __table_args__ = (sa.UniqueConstraint("issuer", "subject", name="issuer_subject"),)

    user_id: Mapped[uuid.UUID] = mapped_column(sa.ForeignKey("users.id", ondelete="CASCADE"))
    issuer: Mapped[str]
    subject: Mapped[str]


class ApiToken(Base, UUIDPkMixin, TimestampMixin):
    """Long-lived personal access token for headless clients (e.g. an iOS
    Shortcut that uploads a receipt straight from the share sheet). Only the
    SHA-256 hash is stored; the raw token (shown once, ``hbk_`` prefix) travels
    in the ``Authorization: Bearer`` header. No expiry — revoke to kill it."""

    __tablename__ = "api_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str]  # user-facing label, e.g. "iOS Kurzbefehl"
    token_hash: Mapped[str] = mapped_column(unique=True)
    last_used_at: Mapped[datetime | None]
    revoked_at: Mapped[datetime | None]
