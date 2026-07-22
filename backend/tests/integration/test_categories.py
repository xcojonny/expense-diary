import httpx
import pytest

pytestmark = pytest.mark.integration


async def _create(client: httpx.AsyncClient, name: str, parent_id: str | None = None) -> dict:
    resp = await client.post(
        "/api/v1/categories", json={"name": name, "parent_id": parent_id}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_top_level_and_child(app_client: httpx.AsyncClient) -> None:
    parent = await _create(app_client, "Testkategorie")
    child = await _create(app_client, "Unterkategorie", parent_id=parent["id"])
    assert child["parent_id"] == parent["id"]


async def test_rejects_duplicate_name_under_same_parent(app_client: httpx.AsyncClient) -> None:
    parent = await _create(app_client, "Eltern")
    await _create(app_client, "Kind", parent_id=parent["id"])
    dup = await app_client.post(
        "/api/v1/categories", json={"name": "Kind", "parent_id": parent["id"]}
    )
    assert dup.status_code == 400


async def test_rename_and_reparent(app_client: httpx.AsyncClient) -> None:
    a = await _create(app_client, "A")
    b = await _create(app_client, "B")
    # rename A, then move it under B
    renamed = await app_client.patch(f"/api/v1/categories/{a['id']}", json={"name": "A2"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "A2"
    moved = await app_client.patch(f"/api/v1/categories/{a['id']}", json={"parent_id": b["id"]})
    assert moved.status_code == 200
    assert moved.json()["parent_id"] == b["id"]


async def test_reparent_cycle_is_rejected(app_client: httpx.AsyncClient) -> None:
    parent = await _create(app_client, "Oben")
    child = await _create(app_client, "Unten", parent_id=parent["id"])
    # making the parent a child of its own child would loop
    resp = await app_client.patch(
        f"/api/v1/categories/{parent['id']}", json={"parent_id": child["id"]}
    )
    assert resp.status_code == 400


async def test_delete_orphans_children_to_top_level(app_client: httpx.AsyncClient) -> None:
    parent = await _create(app_client, "Wurzel")
    child = await _create(app_client, "Zweig", parent_id=parent["id"])
    assert (await app_client.delete(f"/api/v1/categories/{parent['id']}")).status_code == 204

    listing = (await app_client.get("/api/v1/categories")).json()
    surviving = next((c for c in listing if c["id"] == child["id"]), None)
    assert surviving is not None  # child survived
    assert surviving["parent_id"] is None  # and became top-level (FK SET NULL)


async def test_unknown_parent_rejected(app_client: httpx.AsyncClient) -> None:
    resp = await app_client.post(
        "/api/v1/categories",
        json={"name": "X", "parent_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert resp.status_code == 400
