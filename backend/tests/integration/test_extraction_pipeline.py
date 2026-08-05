"""Die Pipeline von Upload bis Positionen — ohne Redis, ohne Worker-Container.

Deckt die drei Wege aus `services/extraction`: Text-PDF (ohne Modell),
Vision-Modell und „kein Modell konfiguriert".
"""

from __future__ import annotations

import httpx

from app.integrations.llm import LlmError, set_vision_model
from tests.conftest import (
    PNG_BYTES,
    REWE_RECEIPT_LINES,
    FakeVisionModel,
    drain_jobs,
    make_text_pdf,
)

VISION_JSON = """
{
  "store_name": "EDEKA", "purchased_at": "2026-03-04", "currency": "EUR",
  "total": 3.58, "confidence": "high",
  "items": [
    {"name": "H-Milch 3,5%", "quantity": 1, "unit": "stk", "unit_price": 1.09,
     "total_price": 1.09, "type": "product", "category": "Milchprodukte & Eier"},
    {"name": "Butter", "quantity": 1, "unit": "stk", "unit_price": 2.49,
     "total_price": 2.49, "type": "product", "category": "Milchprodukte & Eier"}
  ]
}
"""


async def _upload(client: httpx.AsyncClient, data: bytes, name: str, content_type: str) -> int:
    response = await client.post("/api/receipts", files={"file": (name, data, content_type)})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


async def test_text_pdf_is_extracted_without_any_model(client: httpx.AsyncClient) -> None:
    """Der eBon-Normalfall: kein Modell, keine Kosten, Status `done`."""
    receipt_id = await _upload(
        client, make_text_pdf(REWE_RECEIPT_LINES), "ebon.pdf", "application/pdf"
    )
    assert await drain_jobs() == 1

    receipt = (await client.get(f"/api/receipts/{receipt_id}")).json()
    assert receipt["status"] == "done"
    assert receipt["store_name"] == "REWE"
    assert receipt["total_cents"] == 471
    assert receipt["confidence"] == "high"

    names = [item["name"] for item in receipt["line_items"]]
    assert "H-MILCH 3,5%" in names
    kinds = {item["name"]: item["kind"] for item in receipt["line_items"]}
    assert kinds["PFAND 0,25"] == "deposit"
    assert kinds["RABATT AKTION"] == "discount"


async def test_text_pdf_lines_are_categorized_by_keyword(client: httpx.AsyncClient) -> None:
    """eBons bringen keine Kategorie mit — der Schlüsselwort-Vorschlag greift."""
    receipt_id = await _upload(
        client, make_text_pdf(REWE_RECEIPT_LINES), "ebon.pdf", "application/pdf"
    )
    await drain_jobs()

    receipt = (await client.get(f"/api/receipts/{receipt_id}")).json()
    milk = next(i for i in receipt["line_items"] if i["name"] == "H-MILCH 3,5%")
    assert milk["category_id"] is not None
    assert milk["item_id"] is not None  # am Trend-Anker


async def test_image_goes_through_the_vision_model(client: httpx.AsyncClient) -> None:
    fake = FakeVisionModel(response=VISION_JSON)
    set_vision_model(fake)

    receipt_id = await _upload(client, PNG_BYTES, "foto.png", "image/png")
    assert await drain_jobs() == 1

    receipt = (await client.get(f"/api/receipts/{receipt_id}")).json()
    assert fake.calls == 1
    assert receipt["status"] == "done"
    assert receipt["store_name"] == "EDEKA"
    assert receipt["total_cents"] == 358
    assert len(receipt["line_items"]) == 2


async def test_image_without_model_lands_in_needs_review(client: httpx.AsyncClient) -> None:
    """Das Versprechen „ohne LLM benutzbar": kein Absturz, sondern manuelle Erfassung."""
    receipt_id = await _upload(client, PNG_BYTES, "foto.png", "image/png")
    assert await drain_jobs() == 1

    receipt = (await client.get(f"/api/receipts/{receipt_id}")).json()
    assert receipt["status"] == "needs_review"
    assert "LLM_PROVIDER=none" in receipt["error"]


async def test_sum_mismatch_forces_review(client: httpx.AsyncClient) -> None:
    mismatched = VISION_JSON.replace('"total": 3.58', '"total": 99.00')
    set_vision_model(FakeVisionModel(response=mismatched))

    receipt_id = await _upload(client, PNG_BYTES, "foto.png", "image/png")
    await drain_jobs()

    receipt = (await client.get(f"/api/receipts/{receipt_id}")).json()
    assert receipt["status"] == "needs_review"
    assert receipt["confidence"] == "medium"


async def test_model_error_fails_the_receipt_with_a_readable_message(
    client: httpx.AsyncClient,
) -> None:
    set_vision_model(FakeVisionModel(error=LlmError("openai:gpt-4o: HTTP 401: invalid key")))

    receipt_id = await _upload(client, PNG_BYTES, "foto.png", "image/png")
    await drain_jobs()

    receipt = (await client.get(f"/api/receipts/{receipt_id}")).json()
    assert receipt["status"] == "failed"
    # Der Providertext steht am Bon — dort sucht man ihn (ADR-002).
    assert "HTTP 401" in receipt["error"]


async def test_unparseable_model_answer_fails_the_receipt(client: httpx.AsyncClient) -> None:
    set_vision_model(FakeVisionModel(response="Tut mir leid, das kann ich nicht lesen."))

    receipt_id = await _upload(client, PNG_BYTES, "foto.png", "image/png")
    await drain_jobs()

    assert (await client.get(f"/api/receipts/{receipt_id}")).json()["status"] == "failed"


async def test_one_broken_receipt_does_not_block_the_queue(client: httpx.AsyncClient) -> None:
    """Ein kaputter Bon darf die Extraktion der anderen nicht verhindern."""
    set_vision_model(FakeVisionModel(response="kaputt"))
    broken = await _upload(client, PNG_BYTES, "kaputt.png", "image/png")
    good = await _upload(client, make_text_pdf(REWE_RECEIPT_LINES), "ebon.pdf", "application/pdf")

    assert await drain_jobs() == 2
    assert (await client.get(f"/api/receipts/{broken}")).json()["status"] == "failed"
    assert (await client.get(f"/api/receipts/{good}")).json()["status"] == "done"


async def test_reprocess_replaces_line_items_instead_of_duplicating(
    client: httpx.AsyncClient,
) -> None:
    receipt_id = await _upload(
        client, make_text_pdf(REWE_RECEIPT_LINES), "ebon.pdf", "application/pdf"
    )
    await drain_jobs()
    before = len((await client.get(f"/api/receipts/{receipt_id}")).json()["line_items"])

    assert (await client.post(f"/api/receipts/{receipt_id}/reprocess")).status_code == 200
    await drain_jobs()

    after = (await client.get(f"/api/receipts/{receipt_id}")).json()
    assert len(after["line_items"]) == before
    assert after["status"] == "done"


async def test_review_can_be_confirmed_by_hand(client: httpx.AsyncClient) -> None:
    receipt_id = await _upload(client, PNG_BYTES, "foto.png", "image/png")
    await drain_jobs()
    assert (await client.get(f"/api/receipts/{receipt_id}")).json()["status"] == "needs_review"

    confirmed = await client.post(f"/api/receipts/{receipt_id}/reviewed")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "done"
    assert confirmed.json()["error"] is None


async def test_stale_running_jobs_are_requeued_on_start(client: httpx.AsyncClient) -> None:
    """Crash-Recovery: ein Neustart mitten in der Extraktion verliert nichts."""
    import sqlalchemy as sa

    from app.db.session import get_sessionmaker
    from app.models import Job, JobStatus
    from app.services import jobs as jobs_service

    receipt_id = await _upload(
        client, make_text_pdf(REWE_RECEIPT_LINES), "ebon.pdf", "application/pdf"
    )

    async with get_sessionmaker()() as session:
        await session.execute(
            sa.update(Job)
            .where(Job.receipt_id == receipt_id)
            .values(status=JobStatus.RUNNING.value)
        )
        await session.commit()

        assert await jobs_service.requeue_stale(session) == 1

    assert await drain_jobs() == 1
    assert (await client.get(f"/api/receipts/{receipt_id}")).json()["status"] == "done"


async def test_failed_job_is_retried_until_max_attempts(client: httpx.AsyncClient) -> None:
    import sqlalchemy as sa

    from app.db.session import get_sessionmaker
    from app.models import Job

    set_vision_model(FakeVisionModel(response="kaputt"))
    receipt_id = await _upload(client, PNG_BYTES, "foto.png", "image/png")
    await drain_jobs()

    async with get_sessionmaker()() as session:
        job = (
            await session.execute(sa.select(Job).where(Job.receipt_id == receipt_id))
        ).scalar_one()
        # Erster Versuch fehlgeschlagen → erneut eingeplant, mit Backoff.
        assert job.attempts == 1
        assert job.status == "queued"
        assert job.run_after is not None
        assert job.error is not None
