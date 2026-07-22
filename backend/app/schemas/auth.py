from pydantic import BaseModel, EmailStr


class MagicLinkRequest(BaseModel):
    email: EmailStr


class TokenRequest(BaseModel):
    token: str


class SessionOut(BaseModel):
    access_token: str
    token_type: str = "bearer"


class VerifyResponse(BaseModel):
    """Verifying a login link in the bound browser returns a session; opened in
    another browser it returns a pairing code to type into the first one."""

    status: str  # "session" | "code"
    access_token: str | None = None
    code: str | None = None  # formatted pairing code (e.g. "ABC-234")


class LoginStatusResponse(BaseModel):
    status: str  # "pending" | "code" | "used"


class CodeRequest(BaseModel):
    code: str


class AuthConfigOut(BaseModel):
    oidc_enabled: bool
    oidc_provider_name: str
