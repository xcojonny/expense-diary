import uuid

from pydantic import BaseModel


class MembershipOut(BaseModel):
    group_id: uuid.UUID
    group_name: str
    role: str


class MeOut(BaseModel):
    id: uuid.UUID
    email: str
    display_name: str
    is_instance_admin: bool
    memberships: list[MembershipOut]
