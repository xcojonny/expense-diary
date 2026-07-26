import uuid

from pydantic import BaseModel, EmailStr, Field


class GroupOut(BaseModel):
    id: uuid.UUID
    name: str
    role: str  # the current user's role in this group


class GroupCreate(BaseModel):
    name: str = Field(min_length=1)


class InvitationCreate(BaseModel):
    email: EmailStr
    role: str = "member"
