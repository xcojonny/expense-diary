"""SQLAlchemy models. Importing this package registers every table on
``Base.metadata`` so Alembic autogenerate and ``create_all`` see them all.
"""

from app.models.category import Category
from app.models.item import Item
from app.models.line_item import LineItem, LineType
from app.models.receipt import Receipt, ReceiptStatus

__all__ = [
    "Category",
    "Item",
    "LineItem",
    "LineType",
    "Receipt",
    "ReceiptStatus",
]
