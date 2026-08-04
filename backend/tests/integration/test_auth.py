"""Login, Session, Schutz der Endpoints (ADR-004)."""

from __future__ import annotations

import httpx

from app.api.routes import auth as auth_routes
from tests.conftest import TEST_PASSWORD


async def test_session_is_anonymous_before_login(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get("/api/auth/session")
    assert response.status_code == 200
    body = response.json()
    assert body == {"authenticated": False, "auth_mode": "password", "login_required": True}


async def test_login_with_wrong_password_is_rejected(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.post("/api/auth/login", json={"password": "falsch"})
    assert response.status_code == 401


async def test_login_sets_httponly_cookie(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert response.status_code == 200
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie.replace("samesite", "SameSite")

    session = await anon_client.get("/api/auth/session")
    assert session.json()["authenticated"] is True


async def test_protected_endpoint_needs_auth(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.get("/api/receipts")).status_code == 401


async def test_protected_endpoint_works_when_logged_in(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/receipts")).status_code == 200


async def test_logout_clears_the_session(client: httpx.AsyncClient) -> None:
    assert (await client.post("/api/auth/logout")).status_code == 204
    assert (await client.get("/api/receipts")).status_code == 401


async def test_login_is_rate_limited(anon_client: httpx.AsyncClient) -> None:
    """Prozesslokaler Zähler statt Redis — gleiche Wirkung (ADR-002)."""
    auth_routes.reset_login_limiter()
    codes = [
        (await anon_client.post("/api/auth/login", json={"password": "falsch"})).status_code
        for _ in range(11)
    ]
    assert codes[:10] == [401] * 10
    assert codes[10] == 429


async def test_health_is_reachable_without_auth(anon_client: httpx.AsyncClient) -> None:
    """Der Docker-Healthcheck hat kein Cookie."""
    response = await anon_client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["auth_mode"] == "password"
    assert body["llm_ready"] is False  # LLM_PROVIDER=none im Test
