"""Kategorien: CRUD und die drei Regeln, die die DB allein nicht durchsetzt."""

from __future__ import annotations

import httpx


async def test_seeded_tree_is_available(client: httpx.AsyncClient) -> None:
    categories = (await client.get("/api/categories")).json()
    names = {c["name"] for c in categories}
    assert "Obst & Gemüse" in names
    assert "Haushalt & Reinigung" in names
    # Unterkategorien sind wirklich verhängt.
    assert any(c["parent_id"] is not None for c in categories)


async def test_is_food_flag_is_seeded_correctly(client: httpx.AsyncClient) -> None:
    """ADR-007: ein Feld, keine Namensliste im Code."""
    categories = {c["name"]: c["is_food"] for c in (await client.get("/api/categories")).json()}
    assert categories["Obst & Gemüse"] is True
    assert categories["Haushalt & Reinigung"] is False
    assert categories["Tierbedarf"] is False


async def test_create_and_rename(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/categories", json={"name": "Feinkost", "is_food": True})
    assert created.status_code == 201
    category_id = created.json()["id"]

    renamed = await client.patch(f"/api/categories/{category_id}", json={"name": "Delikatessen"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Delikatessen"


async def test_renaming_does_not_change_the_food_flag(client: httpx.AsyncClient) -> None:
    """Der Fehler des Altstands: umbenennen machte „Drogerie" stillschweigend
    zum Lebensmittel, weil die Zuordnung am Namen hing."""
    categories = (await client.get("/api/categories")).json()
    drugstore = next(c for c in categories if c["name"] == "Drogerie & Körperpflege")

    renamed = await client.patch(f"/api/categories/{drugstore['id']}", json={"name": "Drogerie"})
    assert renamed.json()["is_food"] is False


async def test_duplicate_name_under_same_parent_is_rejected(client: httpx.AsyncClient) -> None:
    """Top-Level: der Unique-Index greift hier nicht (SQLite, NULLs distinct)."""
    await client.post("/api/categories", json={"name": "Feinkost"})
    duplicate = await client.post("/api/categories", json={"name": "feinkost"})
    assert duplicate.status_code == 400
    assert "existiert" in duplicate.json()["detail"]


async def test_same_name_under_different_parents_is_allowed(client: httpx.AsyncClient) -> None:
    parent_a = (await client.post("/api/categories", json={"name": "Regal A"})).json()
    parent_b = (await client.post("/api/categories", json={"name": "Regal B"})).json()

    first = await client.post("/api/categories", json={"name": "Sonstiges2", "parent_id": parent_a["id"]})
    second = await client.post("/api/categories", json={"name": "Sonstiges2", "parent_id": parent_b["id"]})
    assert (first.status_code, second.status_code) == (201, 201)


async def test_subcategory_inherits_food_flag_as_default(client: httpx.AsyncClient) -> None:
    categories = (await client.get("/api/categories")).json()
    household = next(c for c in categories if c["name"] == "Haushalt & Reinigung")

    child = await client.post(
        "/api/categories", json={"name": "Waschmittel", "parent_id": household["id"]}
    )
    assert child.json()["is_food"] is False


async def test_cycle_is_rejected(client: httpx.AsyncClient) -> None:
    parent = (await client.post("/api/categories", json={"name": "Ebene 1"})).json()
    child = (
        await client.post("/api/categories", json={"name": "Ebene 2", "parent_id": parent["id"]})
    ).json()

    # Das Elternteil unter sein eigenes Kind hängen.
    response = await client.patch(f"/api/categories/{parent['id']}", json={"parent_id": child["id"]})
    assert response.status_code == 400
    assert "sich selbst" in response.json()["detail"]


async def test_self_parent_is_rejected(client: httpx.AsyncClient) -> None:
    category = (await client.post("/api/categories", json={"name": "Allein"})).json()
    response = await client.patch(
        f"/api/categories/{category['id']}", json={"parent_id": category["id"]}
    )
    assert response.status_code == 400


async def test_unknown_parent_is_rejected(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/categories", json={"name": "Waise", "parent_id": 99999})
    assert response.status_code == 400


async def test_clear_parent_moves_to_top_level(client: httpx.AsyncClient) -> None:
    parent = (await client.post("/api/categories", json={"name": "Oben"})).json()
    child = (
        await client.post("/api/categories", json={"name": "Unten", "parent_id": parent["id"]})
    ).json()

    response = await client.patch(f"/api/categories/{child['id']}", json={"clear_parent": True})
    assert response.json()["parent_id"] is None


async def test_delete_keeps_line_items_and_promotes_children(client: httpx.AsyncClient) -> None:
    """Eine gelöschte Kategorie darf niemals Ausgaben mitnehmen."""
    from tests.conftest import PNG_BYTES

    parent = (await client.post("/api/categories", json={"name": "Zu löschen"})).json()
    child = (
        await client.post("/api/categories", json={"name": "Kind", "parent_id": parent["id"]})
    ).json()

    receipt = (
        await client.post("/api/receipts", files={"file": ("b.png", PNG_BYTES, "image/png")})
    ).json()
    line_item = (
        await client.post(
            f"/api/receipts/{receipt['id']}/line-items",
            json={"name": "Etwas", "total_price_cents": 500, "category_id": parent["id"]},
        )
    ).json()

    assert (await client.delete(f"/api/categories/{parent['id']}")).status_code == 204

    detail = (await client.get(f"/api/receipts/{receipt['id']}")).json()
    remaining = next(i for i in detail["line_items"] if i["id"] == line_item["id"])
    assert remaining["category_id"] is None  # SET NULL, nicht gelöscht
    assert remaining["total_price_cents"] == 500

    categories = (await client.get("/api/categories")).json()
    promoted = next(c for c in categories if c["id"] == child["id"])
    assert promoted["parent_id"] is None


async def test_unknown_category_is_404(client: httpx.AsyncClient) -> None:
    assert (await client.patch("/api/categories/99999", json={"name": "X"})).status_code == 404
    assert (await client.delete("/api/categories/99999")).status_code == 404
