import uuid

from pydantic import BaseModel, ConfigDict, Field


class CategoryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    parent_id: uuid.UUID | None
    sort_order: int


class CategoryCreate(BaseModel):
    name: str = Field(min_length=1)
    parent_id: uuid.UUID | None = None
    sort_order: int = 0


class CategoryUpdate(BaseModel):
    """Partial update. A present ``parent_id`` (incl. explicit null → top-level)
    reparents; omitted fields stay unchanged."""

    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1)
    parent_id: uuid.UUID | None = None
    sort_order: int | None = None
