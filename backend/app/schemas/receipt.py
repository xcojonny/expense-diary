import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.line_item import LineType
from app.models.receipt import ReceiptStatus


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    normalized_name: str | None
    quantity: Decimal | None
    unit: str | None
    unit_price: Decimal | None
    total_price: Decimal
    vat_class: str | None
    line_type: LineType
    category_id: uuid.UUID | None
    item_id: uuid.UUID | None


class ReceiptOut(BaseModel):
    """Summary shape for the receipt list and status polling."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    store_name: str | None
    purchased_at: datetime | None
    total: Decimal | None
    currency: str
    status: ReceiptStatus
    confidence: str | None
    created_at: datetime


class ReceiptDetailOut(ReceiptOut):
    error: str | None
    line_items: list[LineItemOut]


class LineItemWrite(BaseModel):
    """Editable line-item fields (manual correction). ``normalized_name`` and
    ``item_id`` are derived server-side from name + type, never client-set."""

    name: str
    quantity: Decimal | None = None
    unit: str | None = None
    unit_price: Decimal | None = None
    total_price: Decimal
    vat_class: str | None = None
    line_type: LineType = LineType.product
    category_id: uuid.UUID | None = None


class ReceiptUpdate(BaseModel):
    """Partial update of the receipt header. Fields left unset stay unchanged;
    ``status`` lets the user confirm a ``needs_review`` receipt as ``done``."""

    model_config = ConfigDict(extra="forbid")

    store_name: str | None = None
    purchased_at: datetime | None = None
    total: Decimal | None = None
    currency: str | None = None
    status: ReceiptStatus | None = None
