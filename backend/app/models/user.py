from __future__ import annotations

from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.api_token import ApiToken
    from app.models.household import HouseholdMember


class User(Base, TimestampMixin):
    """Ein Mensch.

    **Ohne Passwortspalte.** Wer sich anmeldet, tut das über OIDC oder einen
    vertrauten Proxy-Header (ADR-004); im Einzelnutzer-Modus `password` gibt es
    genau einen Datensatz, der das gemeinsame Passwort repräsentiert. Damit
    entfällt Passwort-Hashing, Zurücksetzen und der ganze Anhang.

    `email` ist der Abgleichsschlüssel und wird kleingeschrieben gespeichert —
    SQLite kennt kein CITEXT.
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(sa.String(320), nullable=False, unique=True, index=True)
    display_name: Mapped[str] = mapped_column(sa.String(160), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True, nullable=False)

    # Absichtlich lazy: Mitgliedschaften werden über
    # `services/households.memberships_for` geladen, damit es auch bei einem
    # gerade angelegten Nutzer funktioniert.
    memberships: Mapped[list[HouseholdMember]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    oidc_identities: Mapped[list[OidcIdentity]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )
    api_tokens: Mapped[list[ApiToken]] = relationship(
        back_populates="user", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def label(self) -> str:
        return self.display_name or self.email


class OidcIdentity(Base, TimestampMixin):
    """Verknüpfung `(issuer, subject)` → lokaler Nutzer.

    Der Abgleich läuft über `subject`, nicht über die E-Mail: eine Mailadresse
    kann beim Identity Provider wechseln, `subject` ist stabil.
    """

    __tablename__ = "oidc_identities"
    __table_args__ = (
        sa.UniqueConstraint("issuer", "subject", name="uq_oidc_issuer_subject"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    issuer: Mapped[str] = mapped_column(sa.String(320), nullable=False)
    subject: Mapped[str] = mapped_column(sa.String(320), nullable=False)

    user: Mapped[User] = relationship(back_populates="oidc_identities")
