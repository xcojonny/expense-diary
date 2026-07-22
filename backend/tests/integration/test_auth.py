import httpx
import pytest

from tests.integration.conftest import CapturingMailer

pytestmark = pytest.mark.integration


async def _create_active_user(email: str) -> None:
    from app.db.session import get_sessionmaker
    from app.services import auth_service

    async with get_sessionmaker()() as session:
        await auth_service.create_user(session, email=email, display_name=email.split("@")[0])
        await session.commit()


async def test_protected_endpoints_require_auth(anon_client: httpx.AsyncClient) -> None:
    assert (await anon_client.get("/api/v1/me")).status_code == 401
    assert (await anon_client.get("/api/v1/receipts")).status_code == 401
    assert (await anon_client.get("/api/v1/categories")).status_code == 401


async def test_auth_config_reports_oidc_disabled(anon_client: httpx.AsyncClient) -> None:
    cfg = (await anon_client.get("/api/v1/auth/config")).json()
    assert cfg["oidc_enabled"] is False


async def test_magic_link_login(anon_client: httpx.AsyncClient, mailer: CapturingMailer) -> None:
    await _create_active_user("a@example.org")
    req = await anon_client.post("/api/v1/auth/magic-link", json={"email": "a@example.org"})
    assert req.status_code == 202

    token = mailer.last_token("token")
    verify = await anon_client.post("/api/v1/auth/verify", json={"token": token})
    assert verify.status_code == 200, verify.text
    access = verify.json()["access_token"]

    me = await anon_client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.org"


async def test_magic_link_no_account_enumeration(
    anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    resp = await anon_client.post("/api/v1/auth/magic-link", json={"email": "ghost@example.org"})
    assert resp.status_code == 202  # same answer as a real account
    assert mailer.sent == []  # but nothing was actually sent


async def test_used_token_cannot_be_replayed(
    anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    await _create_active_user("b@example.org")
    await anon_client.post("/api/v1/auth/magic-link", json={"email": "b@example.org"})
    token = mailer.last_token("token")
    assert (await anon_client.post("/api/v1/auth/verify", json={"token": token})).status_code == 200
    # second use of the same single-use token is rejected
    assert (await anon_client.post("/api/v1/auth/verify", json={"token": token})).status_code == 400


async def test_refresh_and_logout(
    anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    await _create_active_user("c@example.org")
    await anon_client.post("/api/v1/auth/magic-link", json={"email": "c@example.org"})
    await anon_client.post("/api/v1/auth/verify", json={"token": mailer.last_token("token")})

    # the verify response set the refresh cookie (httpx keeps it)
    refreshed = await anon_client.post("/api/v1/auth/refresh")
    assert refreshed.status_code == 200
    assert refreshed.json()["access_token"]

    assert (await anon_client.post("/api/v1/auth/logout")).status_code == 204
    # after logout the (rotated) refresh token is revoked
    assert (await anon_client.post("/api/v1/auth/refresh")).status_code == 401


async def test_invitation_flow(
    app_client: httpx.AsyncClient, anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    # app_client is admin of "Testhaushalt"; invite a new member
    invite = await app_client.post(
        "/api/v1/groups/invitations", json={"email": "invitee@example.org", "role": "member"}
    )
    assert invite.status_code == 202, invite.text

    token = mailer.last_token("invite")
    accept = await anon_client.post("/api/v1/auth/invitations/accept", json={"token": token})
    assert accept.status_code == 200, accept.text
    access = accept.json()["access_token"]

    me = (
        await anon_client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"})
    ).json()
    assert me["email"] == "invitee@example.org"
    assert len(me["memberships"]) == 1
    assert me["memberships"][0]["role"] == "member"


async def test_create_group_and_switch(app_client: httpx.AsyncClient) -> None:
    created = await app_client.post("/api/v1/groups", json={"name": "Zweithaushalt"})
    assert created.status_code == 201
    new_group_id = created.json()["id"]

    groups = (await app_client.get("/api/v1/groups")).json()
    assert {g["name"] for g in groups} == {"Testhaushalt", "Zweithaushalt"}

    # operate on the new group via the tenancy header
    listing = await app_client.get("/api/v1/receipts", headers={"X-Group-Id": new_group_id})
    assert listing.status_code == 200
    assert listing.json() == []  # brand-new group has no receipts
