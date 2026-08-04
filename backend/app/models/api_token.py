from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class ApiToken(Base, TimestampMixin):
    """Langlebiges Bearer-Token für headless-Clients.

    Hauptzweck ist der iOS-Kurzbefehl, der einen Bon direkt aus dem
    Teilen-Menü hochlädt (iOS lässt eine PWA kein Share-Target sein). Gespeichert
    wird nur der SHA-256-Hash; im Klartext ist das Token genau einmal — bei der
    Erstellung — zu sehen.
    """

    __tablename__ = "api_tokens"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(sa.String(80), nullable=False)
    token_hash: Mapped[str] = mapped_column(sa.String(64), nullable=False, unique=True, index=True)
    last_used_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
