"""SQLAlchemy models. Importing this package registers every table on
``Base.metadata`` so Alembic autogenerate and ``create_all`` see them all.
"""

from app.models.category import Category
from app.models.group import Group, GroupInvitation, GroupMember
from app.models.item import Item
from app.models.line_item import LineItem, LineType
from app.models.receipt import Receipt, ReceiptStatus
from app.models.user import ApiToken, MagicLinkToken, OidcIdentity, RefreshToken, User

__all__ = [
    "ApiToken",
    "Category",
    "Group",
    "GroupInvitation",
    "GroupMember",
    "Item",
    "LineItem",
    "LineType",
    "MagicLinkToken",
    "OidcIdentity",
    "Receipt",
    "ReceiptStatus",
    "RefreshToken",
    "User",
]
