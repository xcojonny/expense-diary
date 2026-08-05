"""OIDC-Login.

Der Identity Provider wird durch eine Attrappe ersetzt (`FakeOidcClient`) —
getestet wird unser Teil: state-Prüfung, Nutzer-Abgleich über `(issuer, subject)`,
Session-Cookie, Fehlerbehandlung.
"""

from __future__ import annotations

import httpx
import pytest

from app.core.config import AuthMode, Settings
from app.integrations.oidc import OidcError, OidcUser, set_oidc_client
from tests.conftest import FakeOidcClient

ANNA = OidcUser(
    issuer="https://idp.example.org",
    subject="anna-sub-1",
    email="anna@example.org",
    display_name="Anna",
)


@pytest.fixture
def oidc_mode(settings: Settings) -> None:
    settings.auth_mode = AuthMode.OIDC
    # Damit `sso_available` stimmt; die Attrappe spricht ohnehin kein Netz.
    settings.oidc_issuer = "https://idp.example.org"
    settings.oidc_client_id = "expense-diary"
    settings.oidc_client_secret = "geheim"


async def _login(
    client: httpx.AsyncClient, fake: FakeOidcClient
) -> tuple[httpx.Response, str]:
    """Den Browser-Ablauf nachspielen: /login holen, dann mit state zurückkommen."""
    set_oidc_client(fake)  # type: ignore[arg-type]
    start = await client.get("/api/auth/oidc/login", follow_redirects=False)
    assert start.status_code == 307, start.text
    state = fake.states[-1]
    callback = await client.get(
        "/api/auth/oidc/callback",
        params={"code": "der-code", "state": state},
        follow_redirects=False,
    )
    return callback, state


async def test_session_advertises_sso(oidc_mode: None, anon_client: httpx.AsyncClient) -> None:
    body = (await anon_client.get("/api/auth/session")).json()
    assert body["authenticated"] is False
    assert body["auth_mode"] == "oidc"
    assert body["sso_available"] is True
    # Keine Passwortmaske im SSO-Modus.
    assert body["login_required"] is False


async def test_password_login_is_refused_in_oidc_mode(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    response = await anon_client.post("/api/auth/login", json={"password": "egal"})
    assert response.status_code == 400
    assert "Passwort-Login" in response.json()["detail"]


async def test_login_redirects_and_sets_state_cookie(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    set_oidc_client(FakeOidcClient(ANNA))  # type: ignore[arg-type]
    response = await anon_client.get("/api/auth/oidc/login", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("https://idp.example.org/authorize")
    cookie = response.headers["set-cookie"]
    assert "eb_oidc_state" in cookie
    assert "HttpOnly" in cookie


async def test_callback_creates_user_household_and_session(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    callback, _ = await _login(anon_client, FakeOidcClient(ANNA))
    assert callback.status_code == 303
    assert callback.headers["location"].endswith("/")

    body = (await anon_client.get("/api/auth/session")).json()
    assert body["authenticated"] is True
    assert body["user"]["email"] == "anna@example.org"
    assert body["user"]["display_name"] == "Anna"
    # Wer neu kommt, bekommt einen eigenen Haushalt — sonst wäre die App leer
    # und unbenutzbar.
    assert len(body["user"]["memberships"]) == 1
    assert body["user"]["memberships"][0]["role"] == "admin"


async def test_second_login_reuses_the_same_user(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    """Abgleich über `subject` — kein Zwilling, kein zweiter Haushalt."""
    await _login(anon_client, FakeOidcClient(ANNA))
    first = (await anon_client.get("/api/auth/session")).json()

    await anon_client.post("/api/auth/logout")
    await _login(anon_client, FakeOidcClient(ANNA))
    second = (await anon_client.get("/api/auth/session")).json()

    assert second["user"]["id"] == first["user"]["id"]
    assert len(second["user"]["memberships"]) == 1


async def test_changed_email_is_taken_over(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    """Die Mailadresse darf beim Provider wechseln; `subject` bleibt der Anker."""
    await _login(anon_client, FakeOidcClient(ANNA))
    first_id = (await anon_client.get("/api/auth/session")).json()["user"]["id"]

    await anon_client.post("/api/auth/logout")
    renamed = OidcUser(
        issuer=ANNA.issuer,
        subject=ANNA.subject,
        email="anna.neu@example.org",
        display_name="Anna",
    )
    await _login(anon_client, FakeOidcClient(renamed))

    body = (await anon_client.get("/api/auth/session")).json()
    assert body["user"]["id"] == first_id
    assert body["user"]["email"] == "anna.neu@example.org"


async def test_callback_without_state_cookie_is_refused(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    """Ohne passendes state-Cookie ist es womöglich ein untergeschobener Aufruf."""
    set_oidc_client(FakeOidcClient(ANNA))  # type: ignore[arg-type]
    response = await anon_client.get(
        "/api/auth/oidc/callback",
        params={"code": "der-code", "state": "erfunden"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "sso_error" in response.headers["location"]
    assert (await anon_client.get("/api/auth/session")).json()["authenticated"] is False


async def test_callback_with_wrong_state_is_refused(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    fake = FakeOidcClient(ANNA)
    set_oidc_client(fake)  # type: ignore[arg-type]
    await anon_client.get("/api/auth/oidc/login", follow_redirects=False)

    response = await anon_client.get(
        "/api/auth/oidc/callback",
        params={"code": "der-code", "state": "nicht-der-echte"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "sso_error" in response.headers["location"]
    assert (await anon_client.get("/api/auth/session")).json()["authenticated"] is False


async def test_provider_error_lands_on_the_login_page(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    """Ein Browser darf nie auf einer JSON-Fehlerseite landen."""
    fake = FakeOidcClient(ANNA)
    set_oidc_client(fake)  # type: ignore[arg-type]
    await anon_client.get("/api/auth/oidc/login", follow_redirects=False)

    response = await anon_client.get(
        "/api/auth/oidc/callback",
        params={"error": "access_denied", "state": fake.states[-1]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "/login?sso_error=" in response.headers["location"]
    assert "access_denied" in response.headers["location"]


async def test_token_exchange_failure_is_reported(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    fake = FakeOidcClient(error=OidcError("Token-Tausch: HTTP 401: invalid client"))
    callback, _ = await _login(anon_client, fake)
    assert callback.status_code == 303
    assert "sso_error" in callback.headers["location"]
    assert (await anon_client.get("/api/auth/session")).json()["authenticated"] is False


async def test_missing_email_is_reported(
    oidc_mode: None, anon_client: httpx.AsyncClient
) -> None:
    """Ohne E-Mail lässt sich niemand zuordnen — mit klarer Ursache abbrechen."""
    without_email = OidcUser(
        issuer=ANNA.issuer, subject="nobody", email="", display_name="Niemand"
    )
    callback, _ = await _login(anon_client, FakeOidcClient(without_email))
    assert callback.status_code == 303
    assert "sso_error" in callback.headers["location"]
    assert "email" in callback.headers["location"].lower()


async def test_two_oidc_users_are_separated(
    oidc_mode: None, anon_client: httpx.AsyncClient, second_client: httpx.AsyncClient
) -> None:
    """Zwei SSO-Nutzer, zwei Haushalte, getrennte Bons."""
    from tests.conftest import PNG_BYTES

    await _login(anon_client, FakeOidcClient(ANNA))
    bodo = OidcUser(
        issuer=ANNA.issuer, subject="bodo-sub-2", email="bodo@example.org", display_name="Bodo"
    )
    await _login(second_client, FakeOidcClient(bodo))

    upload = await anon_client.post(
        "/api/receipts", files={"file": ("bon.png", PNG_BYTES, "image/png")}
    )
    assert upload.status_code == 201

    assert (await anon_client.get("/api/receipts")).json()["total"] == 1
    assert (await second_client.get("/api/receipts")).json()["total"] == 0
