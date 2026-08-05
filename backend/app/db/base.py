"""Deklarative Basis und gemeinsame Spalten.

Zeitstempel-Konvention: `created_at`/`updated_at` sind **naives UTC**,
`Receipt.purchased_at` ist die **lokale Uhrzeit vom Bon** (so gedruckt, so
gespeichert). Auswertungen gruppieren nach `purchased_at` — bei einem Haushalt
ist das die gewünschte Semantik, weil „Einkauf am 3." lokal gemeint ist.
"""

from __future__ import annotations

from datetime import UTC, datetime

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    """Naives UTC — SQLite speichert keine Zeitzonen, also gar keine erst
    hineinschreiben."""
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        sa.DateTime, default=utcnow, nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False
    )
