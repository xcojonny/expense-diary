"""Abhängigkeiten — und die **einzige** Stelle, an der Identität und Mandant
entstehen (ADR-004).

Zwei Stufen:

1. `require_user` stellt fest, **wer** anfragt (API-Token, Session-Cookie oder
   vertrauter Proxy-Header).
2. `require_household` stellt fest, **für welchen Haushalt** — aus
   `X-Household-Id` bzw. dem Auswahl-Cookie, immer gegen die Mitgliedschaft
   geprüft. Ohne Mitgliedschaft gibt es 403, nicht 404: der Haushalt existiert,
   man darf nur nicht hinein.

Jeder Endpoint, der Bons, Artikel oder Auswertungen anfasst, hängt an
`HouseholdDep`. Damit gibt es genau eine Stelle, an der ein Mandantenleck
entstehen könnte — und die ist getestet.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AuthMode, Settings, get_settings
from app.core.security import read_session_token
from app.db.session import session_scope
from app.integrations.files import FileStore
from app.models import Household, HouseholdMember, User
from app.services import households as households_service
from app.services import tokens as tokens_service
from app.services import users as users_service

SessionDep = Annotated[AsyncSession, Depends(session_scope)]
SettingsDep = Annotated[Settings, Depends(get_settings)]

HOUSEHOLD_HEADER = "X-Household-Id"
HOUSEHOLD_COOKIE = "eb_household"


def get_file_store(settings: SettingsDep) -> FileStore:
    return FileStore(settings.media_dir)


FileStoreDep = Annotated[FileStore, Depends(get_file_store)]


def _unauthorized(detail: str = "Nicht angemeldet.") -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=detail)


async def require_user(request: Request, settings: SettingsDep, session: SessionDep) -> User:
    """Den anfragenden Nutzer bestimmen; 401, wenn keiner feststellbar ist."""
    # 1. API-Token (iOS-Kurzbefehl). Gilt in jedem Auth-Modus.
    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = await tokens_service.resolve(session, authorization[7:].strip())
        if token is not None:
            user = await users_service.get(session, token.user_id)
            if user is not None and user.is_active:
                return user
            raise _unauthorized("Der Nutzer dieses Tokens ist deaktiviert.")

    # 2. Einzelnutzer-Modi: ein impliziter Nutzer, Zugang über Passwort-Cookie
    #    bzw. gar nicht geschützt.
    if not settings.auth_mode.is_multi_user:
        if settings.auth_mode is AuthMode.PASSWORD and not _has_valid_session(request, settings):
            raise _unauthorized()
        return await users_service.ensure_single_user(session, settings)

    # 3. Vertrauter Proxy-Header. Sicher nur, wenn der Proxy ihn überschreibt —
    #    sonst schickt ihn jeder Client selbst (steht so in README und .env.example).
    if settings.auth_mode is AuthMode.TRUSTED_HEADER:
        identifier = request.headers.get(settings.auth_trusted_header, "").strip()
        if not identifier:
            raise _unauthorized(f"Header {settings.auth_trusted_header} fehlt.")
        email = request.headers.get(settings.auth_trusted_email_header, "").strip()
        name = request.headers.get(settings.auth_trusted_name_header, "").strip()
        user = await users_service.get_or_create_by_email(
            session,
            email=email or _as_email(identifier),
            display_name=name or identifier,
        )
        await users_service.ensure_personal_household(session, user)
        return user

    # 4. OIDC: die Session entsteht im Callback, hier wird nur das Cookie gelesen.
    subject = _session_subject(request, settings)
    if subject is None:
        raise _unauthorized()
    user = await users_service.get(session, subject)
    if user is None or not user.is_active:
        raise _unauthorized("Dieser Zugang ist nicht mehr gültig.")
    return user


def _as_email(identifier: str) -> str:
    """Ein Proxy liefert oft nur einen Benutzernamen. Daraus eine stabile,
    eindeutige Kennung machen, damit der Nutzer wiedergefunden wird."""
    return identifier if "@" in identifier else f"{identifier}@trusted-header.local"


def _has_valid_session(request: Request, settings: Settings) -> bool:
    cookie = request.cookies.get(settings.cookie_name)
    if not cookie:
        return False
    return read_session_token(cookie, secret=settings.session_secret) is not None


def _session_subject(request: Request, settings: Settings) -> int | None:
    """Nutzer-ID aus dem Session-Cookie (`user:<id>`)."""
    cookie = request.cookies.get(settings.cookie_name)
    if not cookie:
        return None
    subject = read_session_token(cookie, secret=settings.session_secret)
    if subject is None or not subject.startswith("user:"):
        return None
    try:
        return int(subject.removeprefix("user:"))
    except ValueError:
        return None


UserDep = Annotated[User, Depends(require_user)]


class ActiveHousehold:
    """Der Haushalt dieser Anfrage plus die Rolle des Nutzers darin."""

    def __init__(self, household: Household, member: HouseholdMember) -> None:
        self.household = household
        self.member = member

    @property
    def id(self) -> int:
        return self.household.id

    @property
    def is_admin(self) -> bool:
        return self.member.is_admin


async def require_household(
    request: Request, session: SessionDep, user: UserDep
) -> ActiveHousehold:
    """Aktiven Haushalt auflösen und die Mitgliedschaft prüfen."""
    requested = request.headers.get(HOUSEHOLD_HEADER) or request.cookies.get(HOUSEHOLD_COOKIE)

    if requested:
        try:
            household_id = int(requested)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{HOUSEHOLD_HEADER} muss eine Zahl sein.",
            ) from exc

        member = await households_service.membership(
            session, household_id=household_id, user_id=user.id
        )
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Kein Zugriff auf diesen Haushalt.",
            )
        household = await households_service.get(session, household_id)
        if household is None:  # kann nur bei paralleler Löschung passieren
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Haushalt nicht gefunden."
            )
        return ActiveHousehold(household, member)

    # Ohne Angabe: die früheste Mitgliedschaft. Für Einzelnutzer ist das immer
    # dieselbe, für Mehrbenutzer ein sinnvoller Default.
    memberships = await households_service.memberships_for(session, user.id)
    if not memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dieser Zugang gehört zu keinem Haushalt.",
        )
    member = memberships[0]
    household = await households_service.get(session, member.household_id)
    if household is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Haushalt nicht gefunden."
        )
    return ActiveHousehold(household, member)


HouseholdDep = Annotated[ActiveHousehold, Depends(require_household)]


async def require_household_admin(active: HouseholdDep) -> ActiveHousehold:
    """Für Verwaltungsaktionen: einladen, umbenennen, Mitglieder ändern, löschen."""
    if not active.is_admin:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Dafür braucht es Admin-Rechte in diesem Haushalt.",
        )
    return active


HouseholdAdminDep = Annotated[ActiveHousehold, Depends(require_household_admin)]
