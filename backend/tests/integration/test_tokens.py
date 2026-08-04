"""API-Tokens — der Weg für den iOS-Kurzbefehl."""

from __future__ import annotations

import httpx

from tests.conftest import PNG_BYTES


async def test_token_lifecycle(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/tokens", json={"name": "iPhone"})
    assert created.status_code == 201
    body = created.json()
    assert body["plaintext"].startswith("edb_")
    assert body["token"]["name"] == "iPhone"

    listed = (await client.get("/api/tokens")).json()
    assert [t["name"] for t in listed] == ["iPhone"]
    # Der Klartext ist in der Liste nicht mehr enthalten.
    assert "plaintext" not in listed[0]

    assert (await client.delete(f"/api/tokens/{body['token']['id']}")).status_code == 204
    assert (await client.get("/api/tokens")).json() == []


async def test_headless_upload_with_token(
    client: httpx.AsyncClient, second_client: httpx.AsyncClient
) -> None:
    plaintext = (await client.post("/api/tokens", json={"name": "Kurzbefehl"})).json()["plaintext"]

    # Eigener Client ohne Cookie — nur mit Bearer-Token, wie der Kurzbefehl.
    response = await second_client.post(
        "/api/receipts",
        files={"file": ("bon.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 201
    # Die Quelle wird unterschieden, damit man Kurzbefehl-Uploads erkennt.
    assert response.json()["source"] == "shortcut"


async def test_unknown_token_is_rejected(anon_client: httpx.AsyncClient) -> None:
    response = await anon_client.get(
        "/api/receipts", headers={"Authorization": "Bearer edb_erfunden"}
    )
    assert response.status_code == 401


async def test_revoked_token_stops_working(
    client: httpx.AsyncClient, second_client: httpx.AsyncClient
) -> None:
    created = (await client.post("/api/tokens", json={"name": "Kurz"})).json()
    headers = {"Authorization": f"Bearer {created['plaintext']}"}

    assert (await second_client.get("/api/receipts", headers=headers)).status_code == 200

    await client.delete(f"/api/tokens/{created['token']['id']}")
    assert (await second_client.get("/api/receipts", headers=headers)).status_code == 401


async def test_last_used_is_recorded(
    client: httpx.AsyncClient, second_client: httpx.AsyncClient
) -> None:
    plaintext = (await client.post("/api/tokens", json={"name": "Kurz"})).json()["plaintext"]
    assert (await client.get("/api/tokens")).json()[0]["last_used_at"] is None

    await second_client.get("/api/receipts", headers={"Authorization": f"Bearer {plaintext}"})
    assert (await client.get("/api/tokens")).json()[0]["last_used_at"] is not None


async def test_unknown_token_id_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.delete("/api/tokens/99999")).status_code == 404
