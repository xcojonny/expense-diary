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


async def test_magic_link_login_same_browser(
    anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    await _create_active_user("a@example.org")
    # Requesting sets the browser-binding cookie; verifying in the same client
    # (same cookie) yields a session directly.
    req = await anon_client.post("/api/v1/auth/magic-link", json={"email": "a@example.org"})
    assert req.status_code == 202

    verify = await anon_client.post("/api/v1/auth/verify", json={"token": mailer.last_token()})
    assert verify.status_code == 200, verify.text
    body = verify.json()
    assert body["status"] == "session"
    me = await anon_client.get("/api/v1/me", headers={"Authorization": f"Bearer {body['access_token']}"})
    assert me.status_code == 200
    assert me.json()["email"] == "a@example.org"


async def test_magic_link_no_account_enumeration(
    anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    resp = await anon_client.post("/api/v1/auth/magic-link", json={"email": "ghost@example.org"})
    assert resp.status_code == 202
    assert mailer.sent == []


async def test_link_opened_in_other_browser_needs_pairing_code(
    anon_client: httpx.AsyncClient, second_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    await _create_active_user("b@example.org")
    # Browser A requests the link (gets the login_request cookie).
    await anon_client.post("/api/v1/auth/magic-link", json={"email": "b@example.org"})
    token = mailer.last_token()

    # Browser B (separate cookie jar) opens the link → gets a pairing code, not a session.
    opened = await second_client.post("/api/v1/auth/verify", json={"token": token})
    assert opened.status_code == 200
    assert opened.json()["status"] == "code"
    code = opened.json()["code"]
    assert code

    # Browser A now polls "code" and finishes by entering the code.
    status = await anon_client.post("/api/v1/auth/login-status")
    assert status.json()["status"] == "code"
    done = await anon_client.post("/api/v1/auth/verify-code", json={"code": code})
    assert done.status_code == 200, done.text
    assert done.json()["access_token"]


async def test_wrong_pairing_code_rejected(
    anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    await _create_active_user("d@example.org")
    await anon_client.post("/api/v1/auth/magic-link", json={"email": "d@example.org"})
    # never opened elsewhere; guessing a code fails
    resp = await anon_client.post("/api/v1/auth/verify-code", json={"code": "ZZZ-999"})
    assert resp.status_code == 400


async def test_refresh_reuse_revokes_family(
    anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    await _create_active_user("c@example.org")
    await anon_client.post("/api/v1/auth/magic-link", json={"email": "c@example.org"})
    await anon_client.post("/api/v1/auth/verify", json={"token": mailer.last_token()})

    old_refresh = anon_client.cookies.get("refresh_token")
    assert (await anon_client.post("/api/v1/auth/refresh")).status_code == 200
    new_refresh = anon_client.cookies.get("refresh_token")
    assert new_refresh != old_refresh

    def only_refresh(value: str) -> None:
        anon_client.cookies.clear()  # avoid duplicate cookies in the jar
        anon_client.cookies.set("refresh_token", value, domain="testserver", path="/api/v1/auth")

    # Replaying the rotated-away token is treated as theft → whole family revoked.
    only_refresh(old_refresh)
    assert (await anon_client.post("/api/v1/auth/refresh")).status_code == 401
    # ...so even the current token no longer works.
    only_refresh(new_refresh)
    assert (await anon_client.post("/api/v1/auth/refresh")).status_code == 401


async def test_logout_revokes_session(
    anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    await _create_active_user("e@example.org")
    await anon_client.post("/api/v1/auth/magic-link", json={"email": "e@example.org"})
    await anon_client.post("/api/v1/auth/verify", json={"token": mailer.last_token()})
    assert (await anon_client.post("/api/v1/auth/logout")).status_code == 204
    assert (await anon_client.post("/api/v1/auth/refresh")).status_code == 401


async def test_invitation_flow(
    app_client: httpx.AsyncClient, anon_client: httpx.AsyncClient, mailer: CapturingMailer
) -> None:
    invite = await app_client.post(
        "/api/v1/groups/invitations", json={"email": "invitee@example.org", "role": "member"}
    )
    assert invite.status_code == 202, invite.text

    accept = await anon_client.post(
        "/api/v1/auth/invitations/accept", json={"token": mailer.last_token("invite")}
    )
    assert accept.status_code == 200, accept.text
    access = accept.json()["access_token"]
    me = (
        await anon_client.get("/api/v1/me", headers={"Authorization": f"Bearer {access}"})
    ).json()
    assert me["email"] == "invitee@example.org"
    assert me["memberships"][0]["role"] == "member"


async def test_create_group_and_switch(app_client: httpx.AsyncClient) -> None:
    created = await app_client.post("/api/v1/groups", json={"name": "Zweithaushalt"})
    assert created.status_code == 201
    new_group_id = created.json()["id"]
    groups = (await app_client.get("/api/v1/groups")).json()
    assert {g["name"] for g in groups} == {"Testhaushalt", "Zweithaushalt"}
    listing = await app_client.get("/api/v1/receipts", headers={"X-Group-Id": new_group_id})
    assert listing.status_code == 200
    assert listing.json() == []
