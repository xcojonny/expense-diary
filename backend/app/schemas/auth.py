from pydantic import BaseModel, EmailStr


class MagicLinkRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AuthConfigOut(BaseModel):
    oidc_enabled: bool
    oidc_provider_name: str
