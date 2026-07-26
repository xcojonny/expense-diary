import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ApiTokenCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)


class ApiTokenOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    name: str
    created_at: datetime
    last_used_at: datetime | None = None


class ApiTokenCreated(ApiTokenOut):
    # The raw token, returned exactly once on creation (never stored, never
    # listed again). The client must copy it now.
    token: str
