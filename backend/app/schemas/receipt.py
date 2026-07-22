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
