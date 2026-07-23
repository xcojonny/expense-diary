import httpx
import pytest

pytestmark = pytest.mark.integration

# A minimal but valid PDF (magic bytes `%PDF-`, long enough to sniff) — stands in
# for a Lidl eBon shared into the iOS Shortcut.
PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


async def test_api_token_lifecycle_and_headless_upload(
    app_client: httpx.AsyncClient, anon_client: httpx.AsyncClient
) -> None:
    # Mint a personal token from the (browser) session — raw secret shown once.
    created = await app_client.post("/api/v1/me/tokens", json={"name": "iOS Kurzbefehl"})
    assert created.status_code == 201, created.text
    body = created.json()
    raw = body["token"]
    assert raw.startswith("hbk_")
    assert body["name"] == "iOS Kurzbefehl"

    # It's listed without the secret.
    listing = (await app_client.get("/api/v1/me/tokens")).json()
    assert [t["name"] for t in listing] == ["iOS Kurzbefehl"]
    assert "token" not in listing[0]
    token_id = listing[0]["id"]

    # A headless client (the Shortcut) uploads a receipt with only the token —
    # no browser session, no X-Group-Id (resolved from the owner's membership).
    up = await anon_client.post(
        "/api/v1/receipts",
        headers={"Authorization": f"Bearer {raw}"},
        files={"file": ("bon.pdf", PDF, "application/pdf")},
    )
    assert up.status_code == 201, up.text

    # Revoking blocks further use.
    assert (await app_client.delete(f"/api/v1/me/tokens/{token_id}")).status_code == 204
    assert (await app_client.get("/api/v1/me/tokens")).json() == []
    blocked = await anon_client.post(
        "/api/v1/receipts",
        headers={"Authorization": f"Bearer {raw}"},
        files={"file": ("bon.pdf", PDF, "application/pdf")},
    )
    assert blocked.status_code == 401, blocked.text


async def test_garbage_api_token_rejected(anon_client: httpx.AsyncClient) -> None:
    resp = await anon_client.get(
        "/api/v1/me", headers={"Authorization": "Bearer hbk_not-a-real-token"}
    )
    assert resp.status_code == 401


async def test_token_management_requires_auth(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.get("/api/v1/me/tokens")).status_code == 401
    assert (
        await anon_client.post("/api/v1/me/tokens", json={"name": "x"})
    ).status_code == 401
