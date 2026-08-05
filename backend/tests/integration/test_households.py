"""Haushalte, Rollen, Einladungen."""

from __future__ import annotations

import httpx
import pytest

from app.integrations.mail import set_mailer
from tests.conftest import PNG_BYTES, FakeMailer, as_user

ANNA = as_user("anna@example.org", "Anna")
BODO = as_user("bodo@example.org", "Bodo")
CARLA = as_user("carla@example.org", "Carla")


@pytest.fixture
async def mailer() -> FakeMailer:
    fake = FakeMailer()
    set_mailer(fake)  # type: ignore[arg-type]
    return fake


async def _session(client: httpx.AsyncClient, who: dict[str, str]) -> dict:
    return (await client.get("/api/auth/session", headers=who)).json()


# --- Haushalte ----------------------------------------------------------------


async def test_first_login_creates_a_household(
    multi_user: None, anon_client: httpx.AsyncClient
) -> None:
    body = await _session(anon_client, ANNA)
    assert body["multi_user"] is True
    assert len(body["user"]["memberships"]) == 1
    assert body["user"]["memberships"][0]["role"] == "admin"
    assert "Anna" in body["user"]["memberships"][0]["household_name"]


async def test_create_and_switch_household(
    multi_user: None, anon_client: httpx.AsyncClient
) -> None:
    first = (await _session(anon_client, ANNA))["active_household_id"]

    created = await anon_client.post(
        "/api/households", json={"name": "Ferienwohnung"}, headers=ANNA
    )
    assert created.status_code == 201
    second = created.json()["id"]

    households = (await anon_client.get("/api/households", headers=ANNA)).json()
    assert {h["id"] for h in households} == {first, second}

    # Ohne Angabe bleibt der erste aktiv; der Header übersteuert.
    assert (await anon_client.get("/api/households/active", headers=ANNA)).json()["id"] == first
    active = await anon_client.get(
        "/api/households/active", headers={**ANNA, "X-Household-Id": str(second)}
    )
    assert active.json()["name"] == "Ferienwohnung"


async def test_receipts_follow_the_active_household(
    multi_user: None, anon_client: httpx.AsyncClient
) -> None:
    """Derselbe Mensch, zwei Haushalte — die Bons dürfen sich nicht mischen."""
    await _session(anon_client, ANNA)
    second = (
        await anon_client.post("/api/households", json={"name": "Zweitwohnung"}, headers=ANNA)
    ).json()["id"]

    upload = await anon_client.post(
        "/api/receipts",
        files={"file": ("bon.png", PNG_BYTES, "image/png")},
        headers={**ANNA, "X-Household-Id": str(second)},
    )
    assert upload.status_code == 201

    assert (await anon_client.get("/api/receipts", headers=ANNA)).json()["total"] == 0
    in_second = await anon_client.get(
        "/api/receipts", headers={**ANNA, "X-Household-Id": str(second)}
    )
    assert in_second.json()["total"] == 1


async def test_rename_household_requires_admin(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    await _session(anon_client, ANNA)
    token = await _invite(anon_client, ANNA, "bodo@example.org", role="member")
    await _accept(anon_client, BODO, token)

    household = (await _session(anon_client, ANNA))["active_household_id"]
    headers = {**BODO, "X-Household-Id": str(household)}

    response = await anon_client.patch(
        "/api/households/active", json={"name": "Bodos Bude"}, headers=headers
    )
    assert response.status_code == 403
    assert "Admin" in response.json()["detail"]

    # Für die Admin geht es.
    assert (
        await anon_client.patch(
            "/api/households/active", json={"name": "Neuer Name"}, headers=ANNA
        )
    ).status_code == 200


async def test_single_user_mode_refuses_extra_households(client: httpx.AsyncClient) -> None:
    """Im Passwort-Modus könnte sich ein zweiter Mensch nicht anmelden — dann
    sind mehrere Haushalte irreführend statt hilfreich."""
    response = await client.post("/api/households", json={"name": "Zweiter"})
    assert response.status_code == 400
    assert "AUTH_MODE" in response.json()["detail"]


# --- Einladungen --------------------------------------------------------------


async def _invite(
    client: httpx.AsyncClient, who: dict[str, str], email: str, *, role: str = "member"
) -> str:
    response = await client.post(
        "/api/households/active/invitations", json={"email": email, "role": role}, headers=who
    )
    assert response.status_code == 201, response.text
    link = response.json()["link"]
    return link.split("token=", 1)[1]


async def _accept(client: httpx.AsyncClient, who: dict[str, str], token: str) -> httpx.Response:
    return await client.post(
        "/api/auth/invitations/accept", json={"token": token}, headers=who
    )


async def test_invitation_round_trip(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    await _session(anon_client, ANNA)
    household = (await _session(anon_client, ANNA))["active_household_id"]

    token = await _invite(anon_client, ANNA, "bodo@example.org")
    # Die Mail ging raus und enthält den Link.
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == "bodo@example.org"
    assert token in mailer.last_link()

    accepted = await _accept(anon_client, BODO, token)
    assert accepted.status_code == 200
    body = accepted.json()
    assert body["active_household_id"] == household
    assert {m["household_id"] for m in body["user"]["memberships"]} >= {household}

    members = (await anon_client.get("/api/households/active/members", headers=ANNA)).json()
    assert {m["email"] for m in members} == {"anna@example.org", "bodo@example.org"}
    assert {m["role"] for m in members} == {"admin", "member"}


async def test_invited_member_sees_the_shared_receipts(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    """Der Punkt der ganzen Übung: geteilte Bons."""
    await _session(anon_client, ANNA)
    household = (await _session(anon_client, ANNA))["active_household_id"]
    await anon_client.post(
        "/api/receipts", files={"file": ("bon.png", PNG_BYTES, "image/png")}, headers=ANNA
    )

    token = await _invite(anon_client, ANNA, "bodo@example.org")
    await _accept(anon_client, BODO, token)

    shared = await anon_client.get(
        "/api/receipts", headers={**BODO, "X-Household-Id": str(household)}
    )
    assert shared.json()["total"] == 1


async def test_invitation_is_single_use(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    await _session(anon_client, ANNA)
    token = await _invite(anon_client, ANNA, "bodo@example.org")
    assert (await _accept(anon_client, BODO, token)).status_code == 200

    second = await _accept(anon_client, CARLA, token)
    assert second.status_code == 400
    assert "eingelöst" in second.json()["detail"]


async def test_unknown_invitation_is_rejected(
    multi_user: None, anon_client: httpx.AsyncClient
) -> None:
    response = await _accept(anon_client, BODO, "erfunden-aber-lang-genug")
    assert response.status_code == 400
    assert "unbekannt" in response.json()["detail"]


async def test_expired_invitation_is_rejected(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    import sqlalchemy as sa

    from app.db.base import utcnow
    from app.db.session import get_sessionmaker
    from app.models import Invitation

    await _session(anon_client, ANNA)
    token = await _invite(anon_client, ANNA, "bodo@example.org")

    async with get_sessionmaker()() as session:
        await session.execute(
            sa.update(Invitation).values(expires_at=utcnow().replace(year=2000))
        )
        await session.commit()

    response = await _accept(anon_client, BODO, token)
    assert response.status_code == 400
    assert "abgelaufen" in response.json()["detail"]


async def test_invitation_needs_admin(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    await _session(anon_client, ANNA)
    household = (await _session(anon_client, ANNA))["active_household_id"]
    token = await _invite(anon_client, ANNA, "bodo@example.org")
    await _accept(anon_client, BODO, token)

    response = await anon_client.post(
        "/api/households/active/invitations",
        json={"email": "carla@example.org"},
        headers={**BODO, "X-Household-Id": str(household)},
    )
    assert response.status_code == 403


async def test_inviting_an_existing_member_is_rejected(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    await _session(anon_client, ANNA)
    token = await _invite(anon_client, ANNA, "bodo@example.org")
    await _accept(anon_client, BODO, token)

    response = await anon_client.post(
        "/api/households/active/invitations",
        json={"email": "bodo@example.org"},
        headers=ANNA,
    )
    assert response.status_code == 400
    assert "bereits Mitglied" in response.json()["detail"]


async def test_open_invitations_can_be_listed_and_revoked(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    await _session(anon_client, ANNA)
    token = await _invite(anon_client, ANNA, "bodo@example.org")

    open_list = (
        await anon_client.get("/api/households/active/invitations", headers=ANNA)
    ).json()
    assert [i["email"] for i in open_list] == ["bodo@example.org"]

    assert (
        await anon_client.delete(
            f"/api/households/active/invitations/{open_list[0]['id']}", headers=ANNA
        )
    ).status_code == 204
    assert (await _accept(anon_client, BODO, token)).status_code == 400


async def test_invitation_without_smtp_returns_the_link(
    multi_user: None, anon_client: httpx.AsyncClient
) -> None:
    """Ohne SMTP soll eine Einladung nicht spurlos verschwinden."""
    await _session(anon_client, ANNA)
    response = await anon_client.post(
        "/api/households/active/invitations",
        json={"email": "bodo@example.org"},
        headers=ANNA,
    )
    assert response.status_code == 201
    body = response.json()
    assert body["mail_sent"] is False
    assert "token=" in body["link"]


# --- Rollen und Mitglieder ----------------------------------------------------


async def test_promote_and_remove_member(
    multi_user: None, anon_client: httpx.AsyncClient, mailer: FakeMailer
) -> None:
    await _session(anon_client, ANNA)
    token = await _invite(anon_client, ANNA, "bodo@example.org")
    await _accept(anon_client, BODO, token)

    members = (await anon_client.get("/api/households/active/members", headers=ANNA)).json()
    bodo = next(m for m in members if m["email"] == "bodo@example.org")

    promoted = await anon_client.patch(
        f"/api/households/active/members/{bodo['id']}", json={"role": "admin"}, headers=ANNA
    )
    assert promoted.status_code == 200
    assert promoted.json()["role"] == "admin"

    removed = await anon_client.delete(
        f"/api/households/active/members/{bodo['id']}", headers=ANNA
    )
    assert removed.status_code == 204
    remaining = (await anon_client.get("/api/households/active/members", headers=ANNA)).json()
    assert [m["email"] for m in remaining] == ["anna@example.org"]


async def test_last_admin_cannot_be_removed_or_demoted(
    multi_user: None, anon_client: httpx.AsyncClient
) -> None:
    """Sonst bleibt ein Haushalt ohne jemanden zurück, der ihn verwalten kann."""
    await _session(anon_client, ANNA)
    members = (await anon_client.get("/api/households/active/members", headers=ANNA)).json()
    anna = members[0]

    demoted = await anon_client.patch(
        f"/api/households/active/members/{anna['id']}", json={"role": "member"}, headers=ANNA
    )
    assert demoted.status_code == 400
    assert "letzte Admin" in demoted.json()["detail"]

    removed = await anon_client.delete(
        f"/api/households/active/members/{anna['id']}", headers=ANNA
    )
    assert removed.status_code == 400


async def test_deleting_a_household_removes_its_receipts(
    multi_user: None, anon_client: httpx.AsyncClient
) -> None:
    await _session(anon_client, ANNA)
    second = (
        await anon_client.post("/api/households", json={"name": "Wegwerf"}, headers=ANNA)
    ).json()["id"]
    headers = {**ANNA, "X-Household-Id": str(second)}
    await anon_client.post(
        "/api/receipts", files={"file": ("bon.png", PNG_BYTES, "image/png")}, headers=headers
    )

    assert (await anon_client.delete("/api/households/active", headers=headers)).status_code == 204

    households = (await anon_client.get("/api/households", headers=ANNA)).json()
    assert second not in {h["id"] for h in households}
    # Der Zugriff auf den gelöschten Haushalt ist danach verboten.
    assert (await anon_client.get("/api/receipts", headers=headers)).status_code == 403
