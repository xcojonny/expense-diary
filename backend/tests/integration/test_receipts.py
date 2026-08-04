"""Upload, Liste, Bearbeitung, Positionen, Löschen."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import PNG_BYTES, make_text_pdf


async def upload(client: httpx.AsyncClient, data: bytes = PNG_BYTES, name: str = "bon.png") -> dict:
    response = await client.post("/api/receipts", files={"file": (name, data, "image/png")})
    assert response.status_code == 201, response.text
    return response.json()


async def test_upload_creates_receipt_in_uploaded_state(client: httpx.AsyncClient) -> None:
    receipt = await upload(client)
    assert receipt["status"] == "uploaded"
    assert receipt["file_media_type"] == "image/png"
    assert receipt["source"] == "upload"
    assert receipt["line_items"] == []


async def test_upload_detects_type_from_magic_bytes_not_content_type(
    client: httpx.AsyncClient,
) -> None:
    """Der Client behauptet PNG, die Bytes sind ein PDF — die Bytes gewinnen."""
    response = await client.post(
        "/api/receipts", files={"file": ("luege.png", make_text_pdf(["X 1,00"]), "image/png")}
    )
    assert response.status_code == 201
    assert response.json()["file_media_type"] == "application/pdf"


async def test_upload_rejects_unsupported_type(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/receipts", files={"file": ("notiz.txt", b"nur Text", "text/plain")}
    )
    assert response.status_code == 422
    assert "JPEG" in response.json()["detail"]


async def test_upload_rejects_empty_file(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/receipts", files={"file": ("leer.png", b"", "image/png")})
    assert response.status_code == 422


async def test_upload_rejects_oversized_file(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "upload_max_bytes", 10)
    response = await client.post("/api/receipts", files={"file": ("gross.png", PNG_BYTES, "image/png")})
    assert response.status_code == 422
    assert "MB" in response.json()["detail"]


async def test_list_receipts_is_paginated(client: httpx.AsyncClient) -> None:
    for _ in range(3):
        await upload(client)

    response = await client.get("/api/receipts", params={"limit": 2})
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert "line_item_count" in body["items"][0]


async def test_list_receipts_filters_by_status(client: httpx.AsyncClient) -> None:
    await upload(client)
    assert (await client.get("/api/receipts", params={"status": "uploaded"})).json()["total"] == 1
    assert (await client.get("/api/receipts", params={"status": "done"})).json()["total"] == 0


async def test_list_receipts_rejects_unknown_status(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/receipts", params={"status": "quatsch"})
    assert response.status_code == 400


async def test_get_unknown_receipt_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/receipts/99999")).status_code == 404


async def test_original_file_is_served_authenticated(client: httpx.AsyncClient) -> None:
    receipt = await upload(client)
    response = await client.get(f"/api/receipts/{receipt['id']}/file")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.content == PNG_BYTES

    # Ohne Session kein Beleg — deshalb gibt es keinen offenen /media-Mount.
    await client.post("/api/auth/logout")
    assert (await client.get(f"/api/receipts/{receipt['id']}/file")).status_code == 401


async def test_update_header(client: httpx.AsyncClient) -> None:
    receipt = await upload(client)
    response = await client.patch(
        f"/api/receipts/{receipt['id']}",
        json={"store_name": "REWE", "total_cents": 1234, "purchased_at": "2026-03-04T17:42:00"},
    )
    assert response.status_code == 200
    body = response.json()
    assert (body["store_name"], body["total_cents"]) == ("REWE", 1234)
    assert body["purchased_at"].startswith("2026-03-04T17:42")


async def test_add_update_delete_line_item(client: httpx.AsyncClient) -> None:
    receipt = await upload(client)
    receipt_id = receipt["id"]

    created = await client.post(
        f"/api/receipts/{receipt_id}/line-items",
        json={"name": "H-Milch 3,5%", "total_price_cents": 109, "quantity_milli": 1000, "unit": "stk"},
    )
    assert created.status_code == 201
    line_item = created.json()
    # Stückpreis wird abgeleitet, wenn er fehlt.
    assert line_item["unit_price_cents"] == 109
    # Der Server hat das Produkt-Stammdatum verknüpft — nie der Client.
    assert line_item["item_id"] is not None

    updated = await client.patch(
        f"/api/line-items/{line_item['id']}",
        json={"total_price_cents": 240, "quantity_milli": 2000},
    )
    assert updated.status_code == 200
    assert updated.json()["unit_price_cents"] == 120  # neu abgeleitet

    assert (await client.delete(f"/api/line-items/{line_item['id']}")).status_code == 204
    detail = await client.get(f"/api/receipts/{receipt_id}")
    assert detail.json()["line_items"] == []


async def test_renaming_a_line_item_remaps_to_the_same_trend_anchor(
    client: httpx.AsyncClient,
) -> None:
    """Kern der manuellen Korrektur: eine korrigierte Position muss am selben
    Artikel landen wie eine extrahierte — mit derselben Normalisierung."""
    receipt = await upload(client)
    first = (
        await client.post(
            f"/api/receipts/{receipt['id']}/line-items",
            json={"name": "H-Milch 3,5%", "total_price_cents": 109},
        )
    ).json()

    second = (
        await client.post(
            f"/api/receipts/{receipt['id']}/line-items",
            json={"name": "Tippfehler", "total_price_cents": 109},
        )
    ).json()
    assert second["item_id"] != first["item_id"]

    corrected = await client.patch(
        f"/api/line-items/{second['id']}", json={"name": "H MILCH 3.5"}
    )
    assert corrected.json()["item_id"] == first["item_id"]


async def test_deposit_line_gets_no_item(client: httpx.AsyncClient) -> None:
    """Pfand ist bon-lokal und darf den Artikelkatalog nicht zumüllen."""
    receipt = await upload(client)
    created = await client.post(
        f"/api/receipts/{receipt['id']}/line-items",
        json={"name": "PFAND 0,25", "total_price_cents": 25, "kind": "deposit"},
    )
    assert created.json()["item_id"] is None


async def test_line_item_endpoints_404_on_unknown_id(client: httpx.AsyncClient) -> None:
    assert (await client.patch("/api/line-items/9999", json={"name": "X"})).status_code == 404
    assert (await client.delete("/api/line-items/9999")).status_code == 404


async def test_delete_receipt_removes_line_items(client: httpx.AsyncClient) -> None:
    """Hängt an `PRAGMA foreign_keys=ON` — ohne das Pragma kaskadiert SQLite nicht."""
    receipt = await upload(client)
    await client.post(
        f"/api/receipts/{receipt['id']}/line-items",
        json={"name": "Milch", "total_price_cents": 109},
    )

    assert (await client.delete(f"/api/receipts/{receipt['id']}")).status_code == 204
    assert (await client.get(f"/api/receipts/{receipt['id']}")).status_code == 404


async def test_mark_reviewed_requires_needs_review(client: httpx.AsyncClient) -> None:
    receipt = await upload(client)
    response = await client.post(f"/api/receipts/{receipt['id']}/reviewed")
    assert response.status_code == 400
