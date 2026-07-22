import base64

import httpx
import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.integration

# A tiny but valid 1x1 PNG so detect_media_type accepts the upload.
PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)

FAKE_JSON = """
{
  "store_name": "REWE", "purchased_at": "2026-07-01", "currency": "EUR",
  "total": 1.04, "confidence": "high",
  "items": [
    {"name": "Bio Milch", "quantity": 1, "unit": "stk", "unit_price": 1.29, "total_price": 1.29, "type": "product", "category": "Milchprodukte & Eier"},
    {"name": "PFAND", "total_price": 0.25, "type": "deposit", "category": null},
    {"name": "RABATT", "total_price": -0.50, "type": "discount", "category": null}
  ]
}
"""


class _FakeLLM:
    def __init__(self, payload: str) -> None:
        self.payload = payload

    async def extract(self, *, image_bytes: bytes, media_type: str, prompt: str) -> str:
        return self.payload


async def _upload(client: httpx.AsyncClient) -> str:
    resp = await client.post(
        "/api/v1/receipts",
        files={"file": ("bon.png", PNG_1X1, "image/png")},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["status"] == "uploaded"  # extraction runs after the response
    return str(body["id"])


async def test_upload_creates_receipt(app_client: httpx.AsyncClient) -> None:
    receipt_id = await _upload(app_client)
    listing = await app_client.get("/api/v1/receipts")
    assert listing.status_code == 200
    assert any(r["id"] == receipt_id for r in listing.json())


async def test_upload_rejects_unsupported_type(app_client: httpx.AsyncClient) -> None:
    resp = await app_client.post(
        "/api/v1/receipts",
        files={"file": ("notes.txt", b"just some text, not an image", "text/plain")},
    )
    assert resp.status_code == 415


async def test_extraction_populates_line_items_and_items(
    app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.db.session import get_sessionmaker
    from app.models import Item
    from app.services import extraction_service
    from app.services.extraction_service import run_extraction

    monkeypatch.setattr(extraction_service, "get_vision_llm", lambda *_: _FakeLLM(FAKE_JSON))

    receipt_id = await _upload(app_client)
    await run_extraction(__import__("uuid").UUID(receipt_id))

    detail = (await app_client.get(f"/api/v1/receipts/{receipt_id}")).json()
    assert detail["status"] == "done"
    assert detail["store_name"] == "REWE"
    assert detail["confidence"] == "high"

    lines = {li["name"]: li for li in detail["line_items"]}
    assert set(lines) == {"Bio Milch", "PFAND", "RABATT"}
    milk = lines["Bio Milch"]
    assert milk["line_type"] == "product"
    assert milk["normalized_name"] == "bio milch"
    assert milk["item_id"] is not None
    assert milk["category_id"] is not None
    assert lines["PFAND"]["line_type"] == "deposit"
    assert lines["PFAND"]["item_id"] is None
    assert lines["RABATT"]["item_id"] is None

    # The product produced exactly one Item master row (the trend anchor).
    async with get_sessionmaker()() as session:
        count = (
            await session.execute(
                select(func.count()).select_from(Item).where(Item.normalized_name == "bio milch")
            )
        ).scalar_one()
        assert count == 1


async def test_extraction_without_model_needs_review(app_client: httpx.AsyncClient) -> None:
    # Default LLM_PROVIDER=none → no model → the receipt awaits manual entry.
    import uuid

    from app.services.extraction_service import run_extraction

    receipt_id = await _upload(app_client)
    await run_extraction(uuid.UUID(receipt_id))

    detail = (await app_client.get(f"/api/v1/receipts/{receipt_id}")).json()
    assert detail["status"] == "needs_review"
    assert detail["line_items"] == []


async def _extracted(client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> dict:
    """Upload + run the fake-LLM extraction, return the receipt detail dict."""
    import uuid

    from app.services import extraction_service
    from app.services.extraction_service import run_extraction

    monkeypatch.setattr(extraction_service, "get_vision_llm", lambda *_: _FakeLLM(FAKE_JSON))
    receipt_id = await _upload(client)
    await run_extraction(uuid.UUID(receipt_id))
    return (await client.get(f"/api/v1/receipts/{receipt_id}")).json()


async def test_edit_line_item_remaps_to_new_item(
    app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = await _extracted(app_client, monkeypatch)
    milk = next(li for li in detail["line_items"] if li["name"] == "Bio Milch")

    resp = await app_client.patch(
        f"/api/v1/receipts/{detail['id']}/line-items/{milk['id']}",
        json={"name": "Vollmilch 3,5%", "total_price": "1.29", "line_type": "product"},
    )
    assert resp.status_code == 200, resp.text
    updated = resp.json()
    assert updated["normalized_name"] == "vollmilch 3 5"  # re-normalized from the new name
    assert updated["item_id"] is not None
    assert updated["item_id"] != milk["item_id"]  # re-mapped to a different Item


async def test_add_and_delete_line_item(
    app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = await _extracted(app_client, monkeypatch)
    receipt_id = detail["id"]
    categories = (await app_client.get("/api/v1/categories")).json()
    category_id = categories[0]["id"]

    add = await app_client.post(
        f"/api/v1/receipts/{receipt_id}/line-items",
        json={"name": "Butter", "total_price": "2.19", "line_type": "product", "category_id": category_id},
    )
    assert add.status_code == 201, add.text
    line = add.json()
    assert line["normalized_name"] == "butter"
    assert line["category_id"] == category_id

    after_add = (await app_client.get(f"/api/v1/receipts/{receipt_id}")).json()
    assert len(after_add["line_items"]) == 4

    delete = await app_client.delete(f"/api/v1/receipts/{receipt_id}/line-items/{line['id']}")
    assert delete.status_code == 204
    after_del = (await app_client.get(f"/api/v1/receipts/{receipt_id}")).json()
    assert len(after_del["line_items"]) == 3


async def test_add_line_item_rejects_unknown_category(
    app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = await _extracted(app_client, monkeypatch)
    resp = await app_client.post(
        f"/api/v1/receipts/{detail['id']}/line-items",
        json={
            "name": "X",
            "total_price": "1.00",
            "line_type": "product",
            "category_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert resp.status_code == 400


async def test_update_receipt_header_and_confirm_review(
    app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = await _extracted(app_client, monkeypatch)
    resp = await app_client.patch(
        f"/api/v1/receipts/{detail['id']}",
        json={"store_name": "EDEKA", "status": "done"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["store_name"] == "EDEKA"
    assert resp.json()["status"] == "done"


async def test_delete_receipt(
    app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    detail = await _extracted(app_client, monkeypatch)
    assert (await app_client.delete(f"/api/v1/receipts/{detail['id']}")).status_code == 204
    assert (await app_client.get(f"/api/v1/receipts/{detail['id']}")).status_code == 404
