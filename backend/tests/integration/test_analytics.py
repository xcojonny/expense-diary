from decimal import Decimal

import httpx
import pytest

from tests.integration.test_receipts import _extracted

pytestmark = pytest.mark.integration

# The fake receipt (see test_receipts.FAKE_JSON) is dated 2026-07-01 with:
#   Bio Milch 1.29 (product, Milchprodukte & Eier) · PFAND 0.25 · RABATT -0.50
YEAR, MONTH = 2026, 7


async def test_monthly_report(app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    await _extracted(app_client, monkeypatch)
    report = (
        await app_client.get(f"/api/v1/analytics/monthly?year={YEAR}&month={MONTH}")
    ).json()

    assert Decimal(report["total_spending"]) == Decimal("1.04")
    assert Decimal(report["product_total"]) == Decimal("1.29")
    assert Decimal(report["deposit_total"]) == Decimal("0.25")
    assert Decimal(report["discount_total"]) == Decimal("-0.50")
    assert report["receipt_count"] == 1
    cats = {c["category_name"]: Decimal(c["total"]) for c in report["by_category"]}
    assert cats["Milchprodukte & Eier"] == Decimal("1.29")
    assert report["top_items"][0]["name"] == "Bio Milch"


async def test_monthly_report_empty_month(app_client: httpx.AsyncClient) -> None:
    report = (await app_client.get("/api/v1/analytics/monthly?year=2000&month=1")).json()
    assert Decimal(report["total_spending"]) == Decimal("0")
    assert report["receipt_count"] == 0
    assert report["by_category"] == []


async def test_expensive_and_overbought(
    app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _extracted(app_client, monkeypatch)

    expensive = (
        await app_client.get(f"/api/v1/analytics/expensive?year={YEAR}&month={MONTH}")
    ).json()
    assert Decimal(expensive["food_total"]) == Decimal("1.29")  # milk is food
    top = expensive["by_total_spend"][0]
    assert top["name"] == "Bio Milch"
    assert Decimal(top["share_of_food_budget"]) == Decimal("1")

    overbought = (
        await app_client.get(f"/api/v1/analytics/overbought?year={YEAR}&month={MONTH}")
    ).json()
    assert overbought[0]["name"] == "Bio Milch"
    assert overbought[0]["count"] == 1


async def test_compare_no_previous_month(
    app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _extracted(app_client, monkeypatch)
    cmp = (await app_client.get(f"/api/v1/analytics/compare?year={YEAR}&month={MONTH}")).json()
    assert Decimal(cmp["current_total"]) == Decimal("1.04")
    assert Decimal(cmp["previous_total"]) == Decimal("0")
    assert cmp["delta_pct"] is None


async def test_price_trend(app_client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch) -> None:
    detail = await _extracted(app_client, monkeypatch)
    milk = next(li for li in detail["line_items"] if li["name"] == "Bio Milch")
    trend = (await app_client.get(f"/api/v1/analytics/price-trend/{milk['item_id']}")).json()
    assert len(trend) == 1
    assert trend[0]["day"] == "2026-07-01"
    assert Decimal(trend[0]["unit_price"]) == Decimal("1.2900")
