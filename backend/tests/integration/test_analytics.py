"""Auswertung über die API — von zwei echten Bons bis zur Kennzahl."""

from __future__ import annotations

import httpx
import pytest

from tests.conftest import PNG_BYTES, drain_jobs


async def _receipt(
    client: httpx.AsyncClient, *, store: str, when: str, lines: list[dict]
) -> int:
    """Bon von Hand aufbauen — deterministischer als über die Extraktion.

    Entspricht dem echten Ablauf „Foto hoch, nichts erkannt, per Hand erfasst,
    als geprüft markiert": nur `done`/`needs_review` gehen in die Auswertung ein,
    ein Bon in `uploaded` also nicht.
    """
    created = await client.post("/api/receipts", files={"file": ("b.png", PNG_BYTES, "image/png")})
    receipt_id = created.json()["id"]
    await drain_jobs()  # kein Modell konfiguriert → needs_review

    categories = {c["name"]: c["id"] for c in (await client.get("/api/categories")).json()}
    for line in lines:
        payload = dict(line)
        category_name = payload.pop("category", None)
        if category_name:
            payload["category_id"] = categories[category_name]
        response = await client.post(f"/api/receipts/{receipt_id}/line-items", json=payload)
        assert response.status_code == 201, response.text

    total = sum(int(line["total_price_cents"]) for line in lines)
    await client.patch(
        f"/api/receipts/{receipt_id}",
        json={"store_name": store, "purchased_at": when, "total_cents": total},
    )
    reviewed = await client.post(f"/api/receipts/{receipt_id}/reviewed")
    assert reviewed.status_code == 200, reviewed.text
    return receipt_id


@pytest.fixture
async def march(client: httpx.AsyncClient) -> httpx.AsyncClient:
    """März 2026: zwei Bons, zwei Märkte, Pfand, Rabatt, ein Nicht-Lebensmittel."""
    await _receipt(
        client,
        store="REWE",
        when="2026-03-04T17:00:00",
        lines=[
            {
                "name": "H-Milch 3,5%",
                "total_price_cents": 109,
                "quantity_milli": 1000,
                "unit": "stk",
                "unit_price_cents": 109,
                "category": "Milchprodukte & Eier",
            },
            {
                "name": "Butter",
                "total_price_cents": 249,
                "quantity_milli": 1000,
                "unit": "stk",
                "unit_price_cents": 249,
                "category": "Milchprodukte & Eier",
            },
            {
                "name": "Spülmittel",
                "total_price_cents": 199,
                "category": "Haushalt & Reinigung",
            },
            {"name": "PFAND", "total_price_cents": 25, "kind": "deposit"},
            {"name": "RABATT", "total_price_cents": -50, "kind": "discount"},
        ],
    )
    await _receipt(
        client,
        store="Lidl",
        when="2026-03-18T10:30:00",
        lines=[
            {
                "name": "H MILCH 3.5",  # gleiche Ware, andere Schreibweise
                "total_price_cents": 119,
                "quantity_milli": 1000,
                "unit": "stk",
                "unit_price_cents": 119,
                "category": "Milchprodukte & Eier",
            },
        ],
    )
    return client


async def test_monthly_report_numbers(march: httpx.AsyncClient) -> None:
    report = (await march.get("/api/analytics/monthly", params={"year": 2026, "month": 3})).json()

    # Zählt alle Bons des Monats — auch einen ohne erkannte Positionen.
    assert report["receipt_count"] == 2
    assert report["product_total_cents"] == 109 + 249 + 199 + 119
    assert report["deposit_total_cents"] == 25
    assert report["discount_total_cents"] == -50
    assert report["total_cents"] == 651
    # Nicht-Lebensmittel bleibt aus dem Lebensmittelbudget draußen.
    assert report["food_total_cents"] == 109 + 249 + 119
    assert report["unreviewed_count"] == 0


async def test_monthly_report_breakdowns(march: httpx.AsyncClient) -> None:
    report = (await march.get("/api/analytics/monthly", params={"year": 2026, "month": 3})).json()

    categories = {c["category_name"]: c["total_cents"] for c in report["by_category"]}
    assert categories["Milchprodukte & Eier"] == 477
    assert categories["Haushalt & Reinigung"] == 199

    stores = {s["store_name"]: (s["total_cents"], s["receipt_count"]) for s in report["by_store"]}
    assert stores["REWE"] == (532, 1)
    assert stores["Lidl"] == (119, 1)

    assert report["by_category"][0]["share_bp"] is not None
    assert report["top_items"][0]["name"] == "Butter"  # teuerste Einzelposition


async def test_empty_month_is_all_zeros(march: httpx.AsyncClient) -> None:
    report = (await march.get("/api/analytics/monthly", params={"year": 2026, "month": 1})).json()
    assert report["total_cents"] == 0
    assert report["receipt_count"] == 0
    assert report["by_category"] == []


async def test_item_ranking_groups_spelling_variants(march: httpx.AsyncClient) -> None:
    """Die Normalisierung zahlt sich hier aus: „H-Milch 3,5%" und „H MILCH 3.5"
    sind ein Artikel, zweimal gekauft."""
    ranking = (
        await march.get(
            "/api/analytics/items", params={"year": 2026, "month": 3, "sort": "frequency"}
        )
    ).json()

    top = ranking["items"][0]
    assert top["purchases"] == 2
    assert top["total_spend_cents"] == 228
    assert top["avg_unit_price_cents"] == 114  # (109 + 119) / 2


async def test_item_ranking_by_spend_and_food_share(march: httpx.AsyncClient) -> None:
    ranking = (
        await march.get("/api/analytics/items", params={"year": 2026, "month": 3, "sort": "spend"})
    ).json()

    assert ranking["food_total_cents"] == 477
    names = [i["name"] for i in ranking["items"]]
    assert names[0] == "Butter"  # 249 ist der größte Einzelposten

    butter = ranking["items"][0]
    assert butter["share_of_food_bp"] == 5220  # 249 / 477 ≈ 52,2 %

    detergent = next(i for i in ranking["items"] if i["name"] == "Spülmittel")
    assert detergent["share_of_food_bp"] is None


async def test_item_ranking_by_unit_price(march: httpx.AsyncClient) -> None:
    ranking = (
        await march.get(
            "/api/analytics/items", params={"year": 2026, "month": 3, "sort": "unit_price"}
        )
    ).json()
    assert ranking["items"][0]["name"] == "Butter"
    # Ohne Stückpreis nicht rankbar → nicht in der Liste.
    assert all(i["avg_unit_price_cents"] is not None for i in ranking["items"])


async def test_item_ranking_rejects_unknown_sort(march: httpx.AsyncClient) -> None:
    response = await march.get("/api/analytics/items", params={"sort": "quatsch"})
    assert response.status_code == 422


async def test_price_trend_over_time(march: httpx.AsyncClient) -> None:
    ranking = (
        await march.get(
            "/api/analytics/items", params={"year": 2026, "month": 3, "sort": "frequency"}
        )
    ).json()
    item_id = ranking["items"][0]["item_id"]

    trend = (await march.get(f"/api/analytics/price-trend/{item_id}", params={"months": 60})).json()
    assert [(p["day"], p["unit_price_cents"]) for p in trend["points"]] == [
        ("2026-03-04", 109),
        ("2026-03-18", 119),
    ]


async def test_price_trend_unknown_item_is_404(march: httpx.AsyncClient) -> None:
    assert (await march.get("/api/analytics/price-trend/99999")).status_code == 404


async def test_compare_to_previous_month(client: httpx.AsyncClient) -> None:
    await _receipt(
        client,
        store="REWE",
        when="2026-02-10T10:00:00",
        lines=[{"name": "Milch", "total_price_cents": 1000, "category": "Milchprodukte & Eier"}],
    )
    await _receipt(
        client,
        store="REWE",
        when="2026-03-10T10:00:00",
        lines=[{"name": "Milch", "total_price_cents": 1200, "category": "Milchprodukte & Eier"}],
    )

    comparison = (await client.get("/api/analytics/compare", params={"year": 2026, "month": 3})).json()
    assert comparison["current_cents"] == 1200
    assert comparison["previous_cents"] == 1000
    assert comparison["delta_cents"] == 200
    assert comparison["delta_bp"] == 2000  # +20 %


async def test_compare_without_history_has_no_percentage(client: httpx.AsyncClient) -> None:
    await _receipt(
        client,
        store="REWE",
        when="2026-03-10T10:00:00",
        lines=[{"name": "Milch", "total_price_cents": 1200, "category": "Milchprodukte & Eier"}],
    )
    comparison = (await client.get("/api/analytics/compare", params={"year": 2026, "month": 3})).json()
    assert comparison["delta_bp"] is None


async def test_unreviewed_receipts_are_counted_but_still_included(
    client: httpx.AsyncClient,
) -> None:
    """Ein ungeprüfter Bon zählt mit (sonst wäre das Monatstotal zu niedrig) —
    aber die UI erfährt, dass etwas zu prüfen ist."""
    created = await client.post("/api/receipts", files={"file": ("b.png", PNG_BYTES, "image/png")})
    receipt_id = created.json()["id"]
    await drain_jobs()  # kein Modell → needs_review

    await client.post(
        f"/api/receipts/{receipt_id}/line-items",
        json={"name": "Handerfasst", "total_price_cents": 500},
    )
    now = (await client.get(f"/api/receipts/{receipt_id}")).json()
    assert now["status"] == "needs_review"

    import datetime

    today = datetime.date.today()
    report = (
        await client.get(
            "/api/analytics/monthly", params={"year": today.year, "month": today.month}
        )
    ).json()
    assert report["total_cents"] == 500
    assert report["unreviewed_count"] == 1
    assert report["receipt_count"] == 1
