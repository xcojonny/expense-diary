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
