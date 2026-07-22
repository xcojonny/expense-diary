import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt

from app.core.config import get_settings

ALGORITHM = "HS256"


def generate_token() -> str:
    """256-bit URL-safe token; only its SHA-256 hash is ever persisted."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Pairing codes for cross-browser magic-link logins: short and human-typeable,
# so the alphabet drops the 0/O/1/I/L look-alikes. The code is derived (HMAC)
# from the token id instead of stored — a DB dump alone cannot reveal it, and
# redeeming it additionally requires the requesting browser's cookie secret.
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_LENGTH = 6


def login_code_for(token_id: uuid.UUID) -> str:
    digest = hmac.new(
        get_settings().secret_key.encode(),
        b"magic-link-code:" + token_id.bytes,
        hashlib.sha256,
    ).digest()
    number = int.from_bytes(digest, "big")
    chars = []
    for _ in range(CODE_LENGTH):
        number, index = divmod(number, len(CODE_ALPHABET))
        chars.append(CODE_ALPHABET[index])
    return "".join(chars)


def format_login_code(code: str) -> str:
    return f"{code[:3]}-{code[3:]}"


def normalize_login_code(raw: str) -> str:
    # ASCII only: hmac.compare_digest raises on non-ASCII, so a typo/umlaut must
    # not become a 500.
    return "".join(char for char in raw.upper() if "A" <= char <= "Z" or "0" <= char <= "9")


def matches_login_code(raw_input: str, token_id: uuid.UUID) -> bool:
    return hmac.compare_digest(normalize_login_code(raw_input), login_code_for(token_id))


def create_access_token(user_id: uuid.UUID, *, is_instance_admin: bool) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "adm": is_instance_admin,
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=settings.access_token_ttl_minutes)).timestamp()),
    }
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError on an invalid/expired token."""
    settings = get_settings()
    payload: dict[str, Any] = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("wrong token type")
    return payload
