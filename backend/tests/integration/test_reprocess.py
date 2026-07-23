import uuid

import httpx
import pytest

pytestmark = pytest.mark.integration

PDF = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n"


async def test_reprocess_reruns_extraction(app_client: httpx.AsyncClient) -> None:
    up = await app_client.post(
        "/api/v1/receipts", files={"file": ("bon.pdf", PDF, "application/pdf")}
    )
    assert up.status_code == 201, up.text
    receipt_id = up.json()["id"]

    again = await app_client.post(f"/api/v1/receipts/{receipt_id}/reprocess")
    assert again.status_code == 200, again.text
    body = again.json()
    assert body["id"] == receipt_id
    assert body["status"] in {"uploaded", "processing", "done", "needs_review", "failed"}


async def test_reprocess_unknown_receipt_404(app_client: httpx.AsyncClient) -> None:
    resp = await app_client.post(f"/api/v1/receipts/{uuid.uuid4()}/reprocess")
    assert resp.status_code == 404
