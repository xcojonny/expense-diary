from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.line_item import LineItem


class ReceiptStatus(StrEnum):
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    DONE = "done"
    NEEDS_REVIEW = "needs_review"
    FAILED = "failed"


RECEIPT_STATUSES = tuple(status.value for status in ReceiptStatus)
TERMINAL_STATUSES = (ReceiptStatus.DONE, ReceiptStatus.NEEDS_REVIEW, ReceiptStatus.FAILED)


class Receipt(Base, TimestampMixin):
    """Ein Kassenbon.

    Statusfluss: `uploaded → processing → done | needs_review | failed`.
    `error` hält den Fehlertext der letzten Extraktion — dort sucht man ihn,
    weshalb es keinen Admin-Log-Ring mehr braucht (ADR-002).
    """

    __tablename__ = "receipts"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('uploaded','processing','done','needs_review','failed')",
            name="ck_receipts_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(
        sa.String(20), default=ReceiptStatus.UPLOADED.value, nullable=False, index=True
    )

    store_name: Mapped[str | None] = mapped_column(sa.String(160), nullable=True)
    # Lokale Uhrzeit vom Bon (siehe db/base.py). Auswertungen gruppieren danach.
    purchased_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True, index=True)
    total_cents: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    currency: Mapped[str] = mapped_column(sa.String(8), default="EUR", nullable=False)

    # Serverseitig erzeugter Dateiname (nie der Client-Name), relativ zu MEDIA_DIR.
    file_path: Mapped[str | None] = mapped_column(sa.String(300), nullable=True)
    file_media_type: Mapped[str | None] = mapped_column(sa.String(80), nullable=True)
    source: Mapped[str] = mapped_column(sa.String(20), default="upload", nullable=False)

    raw_text: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    confidence: Mapped[str | None] = mapped_column(sa.String(10), nullable=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)

    line_items: Mapped[list[LineItem]] = relationship(
        back_populates="receipt",
        cascade="all, delete-orphan",
        order_by="LineItem.position",
        # Die API gibt Positionen immer mit aus (Detail) oder zählt sie (Liste).
        # Eager laden verhindert MissingGreenlet beim Serialisieren eines frisch
        # angelegten Bons und spart das N+1 in der Liste.
        lazy="selectin",
    )

    @property
    def is_terminal(self) -> bool:
        return self.status in {s.value for s in TERMINAL_STATUSES}
