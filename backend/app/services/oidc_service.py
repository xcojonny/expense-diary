"""OIDC (OpenID Connect) login against Authelia — or any OIDC provider.

Standard authorization-code flow with a confidential client: discovery →
authorize redirect → code exchange → userinfo. The id_token is not
signature-verified here; instead we call the userinfo endpoint with the freshly
obtained access token over TLS, which is sufficient for a trusted homelab IdP.
"""

from typing import Any

import httpx

from app.core.config import get_settings

_discovery_cache: dict[str, dict[str, Any]] = {}


def oidc_enabled() -> bool:
    s = get_settings()
    return bool(s.oidc_issuer and s.oidc_client_id and s.oidc_client_secret)


def redirect_uri() -> str:
    return f"{get_settings().api_base_url}/api/v1/auth/oidc/callback"


async def _discover() -> dict[str, Any]:
    issuer = get_settings().oidc_issuer.rstrip("/")
    if issuer not in _discovery_cache:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(f"{issuer}/.well-known/openid-configuration")
            resp.raise_for_status()
            _discovery_cache[issuer] = resp.json()
    return _discovery_cache[issuer]


async def authorize_url(state: str) -> str:
    settings = get_settings()
    conf = await _discover()
    params = {
        "client_id": settings.oidc_client_id,
        "response_type": "code",
        "scope": settings.oidc_scopes,
        "redirect_uri": redirect_uri(),
        "state": state,
    }
    query = "&".join(f"{k}={httpx.QueryParams({k: v})[k]}" for k, v in params.items())
    return f"{conf['authorization_endpoint']}?{query}"


async def exchange(code: str) -> dict[str, Any]:
    """Exchange the auth code and return {issuer, subject, email, display_name}."""
    settings = get_settings()
    conf = await _discover()
    async with httpx.AsyncClient(timeout=15) as client:
        token_resp = await client.post(
            conf["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri(),
                "client_id": settings.oidc_client_id,
                "client_secret": settings.oidc_client_secret,
            },
        )
        token_resp.raise_for_status()
        access_token = token_resp.json()["access_token"]

        userinfo_resp = await client.get(
            conf["userinfo_endpoint"], headers={"Authorization": f"Bearer {access_token}"}
        )
        userinfo_resp.raise_for_status()
        info = userinfo_resp.json()

    email = info.get("email")
    if not email:
        raise ValueError("OIDC userinfo enthält keine E-Mail-Adresse.")
    display_name = info.get("name") or info.get("preferred_username") or email.split("@")[0]
    return {
        "issuer": conf.get("issuer", settings.oidc_issuer),
        "subject": str(info["sub"]),
        "email": email,
        "display_name": display_name,
    }
