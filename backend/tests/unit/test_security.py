from __future__ import annotations

import time

from app.core.security import (
    RateLimiter,
    create_session_token,
    generate_api_token,
    hash_api_token,
    read_session_token,
    verify_password,
)

SECRET = "ein-test-secret-mit-genug-laenge-0123456789"


def test_session_round_trip() -> None:
    token = create_session_token("haushalt", secret=SECRET, ttl_seconds=60)
    assert read_session_token(token, secret=SECRET) == "haushalt"


def test_session_rejects_wrong_secret() -> None:
    token = create_session_token("haushalt", secret=SECRET, ttl_seconds=60)
    assert read_session_token(token, secret="anderes-secret") is None


def test_session_rejects_tampered_payload() -> None:
    token = create_session_token("haushalt", secret=SECRET, ttl_seconds=60)
    payload, _, signature = token.partition(".")
    assert read_session_token(f"{payload}x.{signature}", secret=SECRET) is None


def test_session_rejects_expired() -> None:
    token = create_session_token("haushalt", secret=SECRET, ttl_seconds=-1)
    assert read_session_token(token, secret=SECRET) is None


def test_session_rejects_garbage() -> None:
    for raw in ("", "kein-punkt", ".", "a.b"):
        assert read_session_token(raw, secret=SECRET) is None


def test_verify_password() -> None:
    assert verify_password("geheim", "geheim") is True
    assert verify_password("falsch", "geheim") is False
    # Leeres erwartetes Passwort darf nie durchlassen (AUTH_PASSWORD nicht gesetzt).
    assert verify_password("", "") is False


def test_api_token_is_prefixed_and_only_stored_as_hash() -> None:
    plain, digest = generate_api_token()
    assert plain.startswith("edb_")
    assert digest == hash_api_token(plain)
    assert plain not in digest


def test_rate_limiter_blocks_after_limit() -> None:
    limiter = RateLimiter(limit=3, window_seconds=60)
    assert [limiter.check("a") for _ in range(4)] == [True, True, True, False]
    # Anderer Schlüssel ist unabhängig.
    assert limiter.check("b") is True


def test_rate_limiter_window_expires() -> None:
    limiter = RateLimiter(limit=1, window_seconds=1)
    assert limiter.check("a") is True
    assert limiter.check("a") is False
    time.sleep(1.05)
    assert limiter.check("a") is True


def test_rate_limiter_reset() -> None:
    limiter = RateLimiter(limit=1, window_seconds=60)
    limiter.check("a")
    limiter.reset()
    assert limiter.check("a") is True
