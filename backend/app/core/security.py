"""Session-Signatur, Token-Hashing, Rate-Limit — rein und ohne externe Dienste.

Kein JWT-Paket und kein Redis: ein signiertes Cookie ist HMAC über
`subject|ablauf`, und das Rate-Limit ist prozesslokal, weil es genau einen
Prozess gibt (ADR-002, ADR-004).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time

TOKEN_PREFIX = "edb_"
_SEPARATOR = "."


def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def _sign(payload: str, secret: str) -> str:
    digest = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    return _b64encode(digest)


def create_session_token(subject: str, *, secret: str, ttl_seconds: int) -> str:
    """`base64(subject|expiry).signatur` — selbstbeschreibend und zustandslos."""
    payload = f"{subject}|{int(time.time()) + ttl_seconds}"
    encoded = _b64encode(payload.encode())
    return f"{encoded}{_SEPARATOR}{_sign(encoded, secret)}"


def read_session_token(token: str, *, secret: str) -> str | None:
    """Subject zurückgeben, oder `None` bei falscher Signatur / Ablauf."""
    encoded, _, signature = token.partition(_SEPARATOR)
    if not encoded or not signature:
        return None
    # Signatur zuerst, in konstanter Zeit — erst danach wird der Inhalt gelesen.
    if not hmac.compare_digest(signature, _sign(encoded, secret)):
        return None
    try:
        subject, _, expiry = _b64decode(encoded).decode().rpartition("|")
        if not subject or time.time() > int(expiry):
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    return subject


def verify_password(candidate: str, expected: str) -> bool:
    """Konstante Laufzeit — verrät nicht über die Antwortzeit, wie weit ein
    Versuch gekommen ist."""
    if not expected:
        return False
    return hmac.compare_digest(candidate.encode(), expected.encode())


def generate_api_token() -> tuple[str, str]:
    """`(klartext, hash)`. Der Klartext ist danach nicht wiederherstellbar."""
    plain = TOKEN_PREFIX + secrets.token_urlsafe(32)
    return plain, hash_api_token(plain)


def hash_api_token(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


class RateLimiter:
    """Fixes Zeitfenster, prozesslokal.

    Der Altstand hielt dieselben Zähler in Redis — bei einem Prozess ist das
    identisch in der Wirkung und ein Dienst weniger (ADR-002).
    """

    def __init__(self, *, limit: int, window_seconds: int) -> None:
        self._limit = limit
        self._window = window_seconds
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str) -> bool:
        """`True`, wenn der Versuch erlaubt ist (und gezählt wurde)."""
        now = time.monotonic()
        cutoff = now - self._window
        recent = [stamp for stamp in self._hits.get(key, []) if stamp > cutoff]
        if len(recent) >= self._limit:
            self._hits[key] = recent
            return False
        recent.append(now)
        self._hits[key] = recent
        return True

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._hits.clear()
        else:
            self._hits.pop(key, None)
