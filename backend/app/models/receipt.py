import enum
import uuid
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPkMixin

if TYPE_CHECKING:
    from app.models.line_item import LineItem


class ReceiptStatus(enum.StrEnum):
    """Lifecycle of a receipt through the async extraction pipeline.

    The frontend polls the receipt until it leaves ``processing``:
    uploaded → processing → done | needs_review | failed.
    ``needs_review`` means extraction ran but the result needs a human check
    (e.g. the item sum diverges from the printed total, or confidence is low).
    """

    uploaded = "uploaded"
    processing = "processing"
    done = "done"
    needs_review = "needs_review"
    failed = "failed"


_STATUS_VALUES = ", ".join(f"'{s.value}'" for s in ReceiptStatus)


class Receipt(Base, UUIDPkMixin, TimestampMixin):
    __tablename__ = "receipts"
    __table_args__ = (
        sa.CheckConstraint(f"status IN ({_STATUS_VALUES})", name="status"),
    )

    group_id: Mapped[uuid.UUID] = mapped_column(
        sa.ForeignKey("groups.id", ondelete="CASCADE"), index=True
    )
    store_name: Mapped[str | None]
    purchased_at: Mapped[datetime | None]
    total: Mapped[Decimal | None] = mapped_column(sa.Numeric(10, 2))
    currency: Mapped[str] = mapped_column(default="EUR", server_default="EUR")
    status: Mapped[ReceiptStatus] = mapped_column(
        sa.Text, default=ReceiptStatus.uploaded, server_default=ReceiptStatus.uploaded.value
    )
    image_path: Mapped[str]  # server-generated filename, relative to media_dir
    raw_ocr_text: Mapped[str | None]  # raw LLM/OCR output, kept for re-parsing
    confidence: Mapped[str | None]  # high | medium | low, from the extraction
    error: Mapped[str | None]  # failure detail when status = failed

    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="receipt", cascade="all, delete-orphan", passive_deletes=True
    )
