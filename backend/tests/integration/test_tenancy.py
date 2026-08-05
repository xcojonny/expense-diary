"""Mandantentrennung — der wichtigste Test dieser Suite.

Wenn hier etwas durchfällt, sieht ein Haushalt die Bons eines anderen. Deshalb
wird **jeder** Endpoint geprüft, der Bons, Positionen, Artikel oder Auswertungen
anfasst — nicht nur ein Beispiel.

Der Modus ist `trusted_header`: der „Proxy" ist ein Header, den der Testclient
setzt. Damit lassen sich zwei Menschen ohne Identity Provider abbilden.
"""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import PNG_BYTES, as_user, drain_jobs

ANNA = as_user("anna@example.org", "Anna")
BODO = as_user("bodo@example.org", "Bodo")


async def _household_of(client: httpx.AsyncClient, who: dict[str, str]) -> int:
    body = (await client.get("/api/auth/session", headers=who)).json()
    assert body["authenticated"] is True, body
    return int(body["active_household_id"])


async def _upload(client: httpx.AsyncClient, who: dict[str, str]) -> dict:
    response = await client.post(
        "/api/receipts", files={"file": ("bon.png", PNG_BYTES, "image/png")}, headers=who
    )
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def separated(
    multi_user: None, anon_client: httpx.AsyncClient
) -> tuple[httpx.AsyncClient, int, int]:
    """Zwei Menschen, zwei Haushalte, je ein Bon mit Position."""
    anna_household = await _household_of(anon_client, ANNA)
    bodo_household = await _household_of(anon_client, BODO)
    assert anna_household != bodo_household

    for who in (ANNA, BODO):
        receipt = await _upload(anon_client, who)
        created = await anon_client.post(
            f"/api/receipts/{receipt['id']}/line-items",
            json={"name": "H-Milch 3,5%", "total_price_cents": 109},
            headers=who,
        )
        assert created.status_code == 201, created.text

    return anon_client, anna_household, bodo_household


async def test_each_user_gets_an_own_household(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    _, anna_household, bodo_household = separated
    assert anna_household != bodo_household


async def test_receipt_list_shows_only_own_receipts(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    client, _, _ = separated
    for who in (ANNA, BODO):
        page = (await client.get("/api/receipts", headers=who)).json()
        assert page["total"] == 1, f"{who['Remote-User']} sieht {page['total']} Bons"


async def test_foreign_receipt_is_not_found(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    """404, nicht 403: die API verrät nicht, welche IDs es gibt."""
    client, _, _ = separated
    bodos_receipt = (await client.get("/api/receipts", headers=BODO)).json()["items"][0]["id"]

    assert (await client.get(f"/api/receipts/{bodos_receipt}", headers=ANNA)).status_code == 404


async def test_foreign_receipt_cannot_be_changed_or_deleted(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    client, _, _ = separated
    bodos_receipt = (await client.get("/api/receipts", headers=BODO)).json()["items"][0]["id"]

    assert (
        await client.patch(
            f"/api/receipts/{bodos_receipt}", json={"store_name": "Gekapert"}, headers=ANNA
        )
    ).status_code == 404
    assert (
        await client.delete(f"/api/receipts/{bodos_receipt}", headers=ANNA)
    ).status_code == 404
    assert (
        await client.post(f"/api/receipts/{bodos_receipt}/reprocess", headers=ANNA)
    ).status_code == 404
    assert (
        await client.post(f"/api/receipts/{bodos_receipt}/reviewed", headers=ANNA)
    ).status_code == 404
    # Und der Bon steht danach unverändert da.
    unchanged = (await client.get(f"/api/receipts/{bodos_receipt}", headers=BODO)).json()
    assert unchanged["store_name"] is None


async def test_foreign_receipt_file_is_not_served(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    client, _, _ = separated
    bodos_receipt = (await client.get("/api/receipts", headers=BODO)).json()["items"][0]["id"]
    assert (
        await client.get(f"/api/receipts/{bodos_receipt}/file", headers=ANNA)
    ).status_code == 404


async def test_foreign_line_item_cannot_be_touched(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    """`/line-items/{id}` hat keinen Bon im Pfad — ohne den Join auf den Haushalt
    wäre das das offensichtlichste Leck."""
    client, _, _ = separated
    bodos_receipt = (await client.get("/api/receipts", headers=BODO)).json()["items"][0]["id"]
    bodos_line = (await client.get(f"/api/receipts/{bodos_receipt}", headers=BODO)).json()[
        "line_items"
    ][0]["id"]

    assert (
        await client.patch(
            f"/api/line-items/{bodos_line}", json={"name": "Gekapert"}, headers=ANNA
        )
    ).status_code == 404
    assert (await client.delete(f"/api/line-items/{bodos_line}", headers=ANNA)).status_code == 404


async def test_line_item_cannot_be_added_to_a_foreign_receipt(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    client, _, _ = separated
    bodos_receipt = (await client.get("/api/receipts", headers=BODO)).json()["items"][0]["id"]
    response = await client.post(
        f"/api/receipts/{bodos_receipt}/line-items",
        json={"name": "Untergeschoben", "total_price_cents": 999},
        headers=ANNA,
    )
    assert response.status_code == 404


async def test_same_product_becomes_two_items(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    """Beide haben „H-Milch 3,5%" gekauft — das müssen **zwei** Stammdaten sein,
    sonst teilen sich zwei Haushalte einen Preisverlauf."""
    client, _, _ = separated

    item_ids = set()
    for who in (ANNA, BODO):
        receipt_id = (await client.get("/api/receipts", headers=who)).json()["items"][0]["id"]
        detail = (await client.get(f"/api/receipts/{receipt_id}", headers=who)).json()
        item_id = detail["line_items"][0]["item_id"]
        assert item_id is not None
        item_ids.add(item_id)

    assert len(item_ids) == 2


async def test_analytics_are_separated(separated: tuple[httpx.AsyncClient, int, int]) -> None:
    client, _, _ = separated

    # Nur `done`/`needs_review` gehen in die Auswertung ein — also erst die
    # Extraktion laufen lassen (kein Modell → needs_review) und dann bestätigen.
    await drain_jobs()

    for who in (ANNA, BODO):
        receipt_id = (await client.get("/api/receipts", headers=who)).json()["items"][0]["id"]
        await client.patch(
            f"/api/receipts/{receipt_id}",
            json={"purchased_at": "2026-04-10T10:00:00", "total_cents": 109},
            headers=who,
        )
        reviewed = await client.post(f"/api/receipts/{receipt_id}/reviewed", headers=who)
        assert reviewed.status_code == 200, reviewed.text

    for who in (ANNA, BODO):
        report = (
            await client.get(
                "/api/analytics/monthly", params={"year": 2026, "month": 4}, headers=who
            )
        ).json()
        assert report["receipt_count"] == 1
        assert report["total_cents"] == 109

        ranking = (
            await client.get(
                "/api/analytics/items", params={"year": 2026, "month": 4}, headers=who
            )
        ).json()
        assert len(ranking["items"]) == 1


async def test_foreign_price_trend_is_not_found(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    client, _, _ = separated
    bodos_receipt = (await client.get("/api/receipts", headers=BODO)).json()["items"][0]["id"]
    bodos_item = (await client.get(f"/api/receipts/{bodos_receipt}", headers=BODO)).json()[
        "line_items"
    ][0]["item_id"]

    assert (
        await client.get(f"/api/analytics/price-trend/{bodos_item}", headers=ANNA)
    ).status_code == 404
    assert (
        await client.get(f"/api/analytics/price-trend/{bodos_item}", headers=BODO)
    ).status_code == 200


async def test_switching_to_a_foreign_household_is_forbidden(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    """403 statt 404: der Haushalt existiert, man darf nur nicht hinein."""
    client, _, bodo_household = separated
    response = await client.get(
        "/api/receipts", headers={**ANNA, "X-Household-Id": str(bodo_household)}
    )
    assert response.status_code == 403
    assert "Kein Zugriff" in response.json()["detail"]


async def test_nonsense_household_header_is_rejected(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    client, _, _ = separated
    response = await client.get("/api/receipts", headers={**ANNA, "X-Household-Id": "abc"})
    assert response.status_code == 400


async def test_missing_trusted_header_is_unauthorized(
    multi_user: None, anon_client: httpx.AsyncClient
) -> None:
    response = await anon_client.get("/api/receipts")
    assert response.status_code == 401
    assert "Remote-User" in response.json()["detail"]


async def test_api_tokens_are_per_user(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    client, _, _ = separated
    created = await client.post("/api/tokens", json={"name": "Annas iPhone"}, headers=ANNA)
    assert created.status_code == 201
    token_id = created.json()["token"]["id"]

    assert [t["name"] for t in (await client.get("/api/tokens", headers=ANNA)).json()] == [
        "Annas iPhone"
    ]
    # Bodo sieht Annas Token nicht und kann es nicht widerrufen.
    assert (await client.get("/api/tokens", headers=BODO)).json() == []
    assert (await client.delete(f"/api/tokens/{token_id}", headers=BODO)).status_code == 404


async def test_token_upload_lands_in_the_owners_household(
    separated: tuple[httpx.AsyncClient, int, int],
) -> None:
    """Der iOS-Kurzbefehl trägt kein Cookie — der Bon muss trotzdem im Haushalt
    des Token-Besitzers landen."""
    client, _, _ = separated
    plaintext = (
        await client.post("/api/tokens", json={"name": "Kurzbefehl"}, headers=ANNA)
    ).json()["plaintext"]

    response = await client.post(
        "/api/receipts",
        files={"file": ("bon.png", PNG_BYTES, "image/png")},
        headers={"Authorization": f"Bearer {plaintext}"},
    )
    assert response.status_code == 201
    assert response.json()["source"] == "shortcut"

    assert (await client.get("/api/receipts", headers=ANNA)).json()["total"] == 2
    assert (await client.get("/api/receipts", headers=BODO)).json()["total"] == 1
