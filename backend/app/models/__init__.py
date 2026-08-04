"""Datenmodell.

Alle Modelle werden hier importiert, damit Alembics `autogenerate` und
`Base.metadata.create_all` sie kennen.

Beträge heißen `*_cents` und sind Integer, Mengen `quantity_milli`
(Tausendstel) — siehe ADR-003. Primärschlüssel sind Integer (ADR-008).
"""

from app.db.base import Base
from app.models.api_token import ApiToken
from app.models.category import Category
from app.models.item import Item
from app.models.job import Job, JobStatus
from app.models.line_item import LINE_KINDS, LineItem
from app.models.receipt import RECEIPT_STATUSES, Receipt, ReceiptStatus

__all__ = [
    "LINE_KINDS",
    "RECEIPT_STATUSES",
    "ApiToken",
    "Base",
    "Category",
    "Item",
    "Job",
    "JobStatus",
    "LineItem",
    "Receipt",
    "ReceiptStatus",
]
