"""OIDC-Client: Authorization-Code-Flow mit vertraulichem Client.

Absichtlich klein gehalten — kein ID-Token-Signaturcheck, weil der Code direkt
beim Provider gegen das Token getauscht wird (Backchannel über TLS) und die
Nutzerdaten aus dem **Userinfo-Endpoint** kommen. Damit braucht es keine
JWKS-Verarbeitung und keine Krypto-Abhängigkeit.

Der `state` wird als kurzlebiges Cookie gespiegelt (CSRF-Schutz); der Vergleich
läuft in konstanter Zeit.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)

DISCOVERY_PATH = "/.well-known/openid-configuration"
STATE_BYTES = 24


class OidcError(RuntimeError):
    """Der Identity Provider hat einen Fehler gemeldet oder unerwartet geantwortet."""


@dataclass(frozen=True)
class OidcEndpoints:
    authorization: str
    token: str
    userinfo: str
    issuer: str


@dataclass(frozen=True)
class OidcUser:
    issuer: str
    subject: str
    email: str
    display_name: str


class OidcClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # Discovery-Ergebnis für die Prozesslaufzeit merken: es ändert sich
        # praktisch nie und ein Login soll nicht zwei Roundtrips kosten.
        self._endpoints: OidcEndpoints | None = None

    @property
    def configured(self) -> bool:
        return self._settings.oidc_configured

    def new_state(self) -> str:
        return secrets.token_urlsafe(STATE_BYTES)

    async def endpoints(self) -> OidcEndpoints:
        if self._endpoints is not None:
            return self._endpoints

        issuer = self._settings.oidc_issuer.rstrip("/")
        url = f"{issuer}{DISCOVERY_PATH}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(url)
        except httpx.HTTPError as exc:
            raise OidcError(f"Discovery bei {url} fehlgeschlagen: {exc}") from exc

        if response.status_code >= 400:
            raise OidcError(f"Discovery bei {url}: HTTP {response.status_code}")

        try:
            data = response.json()
            self._endpoints = OidcEndpoints(
                authorization=data["authorization_endpoint"],
                token=data["token_endpoint"],
                userinfo=data["userinfo_endpoint"],
                issuer=data.get("issuer", issuer),
            )
        except (KeyError, ValueError) as exc:
            raise OidcError(f"Discovery-Dokument unbrauchbar: {exc}") from exc

        log.info("oidc.discovered", extra={"issuer": self._endpoints.issuer})
        return self._endpoints

    async def authorization_url(self, *, state: str) -> str:
        endpoints = await self.endpoints()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": self._settings.oidc_client_id,
                "redirect_uri": self._settings.oidc_redirect_uri,
                "scope": self._settings.oidc_scopes,
                "state": state,
            }
        )
        separator = "&" if "?" in endpoints.authorization else "?"
        return f"{endpoints.authorization}{separator}{query}"

    async def exchange(self, *, code: str) -> OidcUser:
        """Code gegen Token tauschen und den Nutzer aus Userinfo lesen."""
        endpoints = await self.endpoints()

        try:
            async with httpx.AsyncClient(timeout=20) as client:
                token_response = await client.post(
                    endpoints.token,
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": self._settings.oidc_redirect_uri,
                        "client_id": self._settings.oidc_client_id,
                        "client_secret": self._settings.oidc_client_secret,
                    },
                    headers={"Accept": "application/json"},
                )
                if token_response.status_code >= 400:
                    raise OidcError(
                        f"Token-Tausch: HTTP {token_response.status_code}: "
                        f"{token_response.text[:300]}"
                    )
                access_token = token_response.json().get("access_token")
                if not access_token:
                    raise OidcError("Token-Antwort enthält kein access_token.")

                userinfo_response = await client.get(
                    endpoints.userinfo,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
        except httpx.HTTPError as exc:
            raise OidcError(f"Netzwerkfehler beim Identity Provider: {exc}") from exc

        if userinfo_response.status_code >= 400:
            raise OidcError(
                f"Userinfo: HTTP {userinfo_response.status_code}: "
                f"{userinfo_response.text[:300]}"
            )

        try:
            info = userinfo_response.json()
        except ValueError as exc:
            raise OidcError(f"Userinfo-Antwort ist kein JSON: {exc}") from exc

        subject = str(info.get("sub") or "").strip()
        if not subject:
            raise OidcError("Userinfo ohne 'sub' — damit ist kein Abgleich möglich.")

        name = str(info.get("name") or info.get("preferred_username") or "").strip()
        log.info("oidc.login", extra={"issuer": endpoints.issuer, "subject": subject})
        return OidcUser(
            issuer=endpoints.issuer,
            subject=subject,
            email=str(info.get("email") or "").strip().lower(),
            display_name=name,
        )


# Testeinstiegspunkt: die Tests injizieren einen Fake statt einen HTTP-Server
# zu starten.
_override: OidcClient | None = None


def set_oidc_client(client: OidcClient | None) -> None:
    global _override
    _override = client


def build_oidc_client(settings: Settings) -> OidcClient:
    return _override if _override is not None else OidcClient(settings)
