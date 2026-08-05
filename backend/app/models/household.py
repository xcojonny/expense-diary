from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.item import Item
    from app.models.receipt import Receipt
    from app.models.user import User


class Role(StrEnum):
    ADMIN = "admin"
    MEMBER = "member"


ROLES = tuple(role.value for role in Role)


class Household(Base, TimestampMixin):
    """Der Haushalt ist die **Mandantengrenze** (ADR-004).

    `Receipt` und `Item` gehören genau einem Haushalt; `Category` ist geteiltes
    Stammdatum (siehe ADR-012). Wer mehrere Haushalte in einer Instanz führt,
    hat pro Haushalt einen eigenen Bon-Bestand und Preisverlauf.
    """

    __tablename__ = "households"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(120), nullable=False)

    # `passive_deletes=True` überall: das Löschen erledigt die DB über
    # ON DELETE CASCADE. Ohne das würde die ORM `household_id` auf NULL setzen
    # wollen — die Spalte ist NOT NULL, und der Löschversuch scheitert.
    members: Mapped[list[HouseholdMember]] = relationship(
        back_populates="household", cascade="all, delete-orphan", passive_deletes=True
    )
    invitations: Mapped[list[Invitation]] = relationship(
        back_populates="household", cascade="all, delete-orphan", passive_deletes=True
    )
    receipts: Mapped[list[Receipt]] = relationship(
        back_populates="household", cascade="all, delete-orphan", passive_deletes=True
    )
    items: Mapped[list[Item]] = relationship(
        back_populates="household", cascade="all, delete-orphan", passive_deletes=True
    )


class HouseholdMember(Base, TimestampMixin):
    """Mitgliedschaft mit Rolle. `admin` darf einladen, umbenennen und Mitglieder
    entfernen; `member` darf alles mit Bons und Kategorien."""

    __tablename__ = "household_members"
    __table_args__ = (
        sa.UniqueConstraint("household_id", "user_id", name="uq_members_household_user"),
        sa.CheckConstraint("role IN ('admin','member')", name="ck_members_role"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id: Mapped[int] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(sa.String(12), default=Role.MEMBER.value, nullable=False)

    # `User.memberships` ist selectin, und die Session-Antwort braucht den
    # Haushaltsnamen — also diese Richtung eager. Die Gegenrichtungen bleiben
    # lazy, damit die Loader nicht im Kreis laufen.
    household: Mapped[Household] = relationship(back_populates="members", lazy="selectin")
    user: Mapped[User] = relationship(back_populates="memberships")

    @property
    def is_admin(self) -> bool:
        return self.role == Role.ADMIN.value


class Invitation(Base, TimestampMixin):
    """Einladung in einen Haushalt.

    Nur der SHA-256-Hash des Tokens wird gespeichert; der Klartext steht
    ausschließlich im Einladungslink. Einmalig verwendbar und mit Ablaufdatum.
    """

    __tablename__ = "invitations"

    id: Mapped[int] = mapped_column(primary_key=True)
    household_id: Mapped[int] = mapped_column(
        sa.ForeignKey("households.id", ondelete="CASCADE"), nullable=False, index=True
    )
    email: Mapped[str] = mapped_column(sa.String(320), nullable=False)
    role: Mapped[str] = mapped_column(sa.String(12), default=Role.MEMBER.value, nullable=False)
    token_hash: Mapped[str] = mapped_column(
        sa.String(64), nullable=False, unique=True, index=True
    )
    invited_by_user_id: Mapped[int | None] = mapped_column(
        sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)

    household: Mapped[Household] = relationship(back_populates="invitations")
