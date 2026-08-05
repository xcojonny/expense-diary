"""Datenmodell.

Alle Modelle werden hier importiert, damit Alembics `autogenerate` und
`Base.metadata.create_all` sie kennen.

Beträge heißen `*_cents` und sind Integer, Mengen `quantity_milli`
(Tausendstel) — siehe ADR-003. Primärschlüssel sind Integer (ADR-008).
"""

from app.db.base import Base
from app.models.api_token import ApiToken
from app.models.category import Category
from app.models.household import ROLES, Household, HouseholdMember, Invitation, Role
from app.models.item import Item
from app.models.job import Job, JobStatus
from app.models.line_item import LINE_KINDS, LineItem
from app.models.receipt import RECEIPT_STATUSES, Receipt, ReceiptStatus
from app.models.user import OidcIdentity, User

__all__ = [
    "LINE_KINDS",
    "RECEIPT_STATUSES",
    "ROLES",
    "ApiToken",
    "Base",
    "Category",
    "Household",
    "HouseholdMember",
    "Invitation",
    "Item",
    "Job",
    "JobStatus",
    "LineItem",
    "OidcIdentity",
    "Receipt",
    "ReceiptStatus",
    "Role",
    "User",
]
