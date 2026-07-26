import httpx
import pytest

pytestmark = pytest.mark.integration


async def test_admin_can_read_logs(app_client: httpx.AsyncClient) -> None:
    # app_client is an instance admin.
    resp = await app_client.get("/api/v1/admin/logs?limit=50")
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_logs_capture_via_shared_ring(app_client: httpx.AsyncClient) -> None:
    """A logged event is visible through the admin log view — the same path the
    ARQ worker uses to make its extraction/LLM logs visible to the API process."""
    from app.core.logging import get_logger, get_recent_logs

    get_logger("test").info("hello-from-test", marker="abc123")
    logs = get_recent_logs(limit=500)
    assert any(e["event"] == "hello-from-test" for e in logs)

    resp = await app_client.get("/api/v1/admin/logs?limit=500")
    assert resp.status_code == 200, resp.text
    assert any(e["event"] == "hello-from-test" for e in resp.json())


async def test_logs_require_instance_admin(anon_client: httpx.AsyncClient) -> None:
    from app.core.security import create_access_token
    from app.db.session import get_sessionmaker
    from app.services import auth_service

    async with get_sessionmaker()() as session:
        user = await auth_service.create_user(
            session, email="member@example.org", display_name="Member"
        )
        await session.commit()
        token = create_access_token(user.id, is_instance_admin=False)

    # A normal (non-admin) user is forbidden.
    forbidden = await anon_client.get(
        "/api/v1/admin/logs", headers={"Authorization": f"Bearer {token}"}
    )
    assert forbidden.status_code == 403

    # Anonymous is unauthorized.
    assert (await anon_client.get("/api/v1/admin/logs")).status_code == 401
