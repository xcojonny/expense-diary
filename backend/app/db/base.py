import uuid
from datetime import datetime
from typing import Any, ClassVar

import sqlalchemy as sa
from sqlalchemy import MetaData, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from uuid6 import uuid7

# Predictable constraint names so Alembic autogenerate produces stable, human
# diffs and migrations can drop constraints by name.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map: ClassVar[dict[Any, Any]] = {
        str: sa.Text(),
        datetime: sa.DateTime(timezone=True),
        uuid.UUID: PGUUID(as_uuid=True),
    }


class UUIDPkMixin:
    # uuid7 keys are time-ordered → index locality + natural creation ordering.
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())
