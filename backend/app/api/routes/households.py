"""Haushalte, Mitglieder, Einladungen.

Verwaltungsaktionen hängen an `HouseholdAdminDep` — der Rollencheck steht damit
an einer Stelle und nicht in jedem Handler.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response, status

from app.api.deps import (
    HOUSEHOLD_COOKIE,
    HouseholdAdminDep,
    HouseholdDep,
    SessionDep,
    SettingsDep,
    UserDep,
)
from app.core.logging import get_logger
from app.integrations.mail import build_mailer, invitation_email
from app.models import Household
from app.schemas import (
    HouseholdCreate,
    HouseholdOut,
    HouseholdUpdate,
    InvitationCreate,
    InvitationCreated,
    InvitationOut,
    MemberOut,
    MemberUpdate,
)
from app.services import households as households_service

router = APIRouter(prefix="/households", tags=["households"])
log = get_logger(__name__)


def _require_multi_user(settings: SettingsDep) -> None:
    """Einladungen und mehrere Haushalte brauchen einen Modus, in dem sich ein
    zweiter Mensch überhaupt anmelden kann (ADR-004)."""
    if not settings.auth_mode.is_multi_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"AUTH_MODE={settings.auth_mode.value} ist ein Einzelnutzer-Modus. "
                "Für mehrere Haushalte oder Einladungen AUTH_MODE=oidc oder "
                "trusted_header verwenden."
            ),
        )


@router.get("", response_model=list[HouseholdOut])
async def list_households(session: SessionDep, user: UserDep) -> list[Household]:
    """Die Haushalte des angemeldeten Nutzers."""
    return await households_service.list_for_user(session, user)


@router.post("", response_model=HouseholdOut, status_code=status.HTTP_201_CREATED)
async def create_household(
    session: SessionDep, settings: SettingsDep, user: UserDep, payload: HouseholdCreate
) -> Household:
    _require_multi_user(settings)
    try:
        household = await households_service.create(session, name=payload.name, owner=user)
    except households_service.HouseholdError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    log.info("household.created", extra={"household_id": household.id, "user_id": user.id})
    return household


@router.get("/active", response_model=HouseholdOut)
async def read_active(household: HouseholdDep) -> Household:
    return household.household


@router.post("/{household_id}/activate", response_model=HouseholdOut)
async def switch_active(
    response: Response,
    session: SessionDep,
    settings: SettingsDep,
    user: UserDep,
    household_id: int,
) -> Household:
    """Aktiven Haushalt wechseln. Die Auswahl liegt in einem Cookie, damit sie
    einen Neuladen überlebt; der Header `X-Household-Id` übersteuert sie."""
    member = await households_service.membership(
        session, household_id=household_id, user_id=user.id
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Kein Zugriff auf diesen Haushalt."
        )
    household = await households_service.get(session, household_id)
    if household is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Haushalt nicht gefunden."
        )

    response.set_cookie(
        HOUSEHOLD_COOKIE,
        str(household_id),
        max_age=settings.session_ttl_hours * 3600,
        httponly=False,
        secure=settings.cookie_secure,
        samesite="lax",
        path="/",
    )
    return household


@router.patch("/active", response_model=HouseholdOut)
async def rename_active(
    session: SessionDep, household: HouseholdAdminDep, payload: HouseholdUpdate
) -> Household:
    try:
        return await households_service.rename(session, household.household, name=payload.name)
    except households_service.HouseholdError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/active", status_code=status.HTTP_204_NO_CONTENT)
async def delete_active(
    response: Response, session: SessionDep, household: HouseholdAdminDep
) -> None:
    """Haushalt löschen — **mit** allen Bons und Artikeln (FK-Kaskade)."""
    log.info("household.deleted", extra={"household_id": household.id})
    await households_service.delete(session, household.household)
    response.delete_cookie(HOUSEHOLD_COOKIE, path="/")


# --- Mitglieder ---------------------------------------------------------------


@router.get("/active/members", response_model=list[MemberOut])
async def list_members(session: SessionDep, household: HouseholdDep) -> list[MemberOut]:
    return [
        MemberOut(
            id=member.id,
            user_id=member.user_id,
            email=member.user.email,
            display_name=member.user.display_name,
            role=member.role,
        )
        for member in await households_service.members(session, household.id)
    ]


async def _load_member(session: SessionDep, household_id: int, member_id: int) -> object:
    for member in await households_service.members(session, household_id):
        if member.id == member_id:
            return member
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND, detail="Mitglied nicht gefunden."
    )


@router.patch("/active/members/{member_id}", response_model=MemberOut)
async def update_member(
    session: SessionDep, household: HouseholdAdminDep, member_id: int, payload: MemberUpdate
) -> MemberOut:
    member = await _load_member(session, household.id, member_id)
    try:
        updated = await households_service.set_role(session, member, role=payload.role)  # type: ignore[arg-type]
    except households_service.HouseholdError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    return MemberOut(
        id=updated.id,
        user_id=updated.user_id,
        email=updated.user.email,
        display_name=updated.user.display_name,
        role=updated.role,
    )


@router.delete("/active/members/{member_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_member(
    session: SessionDep, household: HouseholdAdminDep, member_id: int
) -> None:
    """Mitglied entfernen. Die Bons bleiben — sie gehören dem Haushalt."""
    member = await _load_member(session, household.id, member_id)
    try:
        await households_service.remove_member(session, member)  # type: ignore[arg-type]
    except households_service.HouseholdError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


# --- Einladungen --------------------------------------------------------------


@router.get("/active/invitations", response_model=list[InvitationOut])
async def list_invitations(session: SessionDep, household: HouseholdAdminDep) -> list[object]:
    return list(await households_service.open_invitations(session, household.id))


@router.post(
    "/active/invitations",
    response_model=InvitationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def invite(
    session: SessionDep,
    settings: SettingsDep,
    household: HouseholdAdminDep,
    user: UserDep,
    payload: InvitationCreate,
) -> InvitationCreated:
    """Einladung anlegen und per Mail verschicken.

    Ohne konfiguriertes SMTP wird der Link nicht verschickt, sondern
    zurückgegeben (und geloggt) — eine Einladung soll nicht spurlos verschwinden.
    """
    _require_multi_user(settings)
    try:
        invitation, token = await households_service.create_invitation(
            session,
            household=household.household,
            email=payload.email,
            role=payload.role,
            invited_by=user,
            ttl_hours=settings.invitation_ttl_hours,
        )
    except households_service.HouseholdError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    link = f"{settings.base_url.rstrip('/')}/einladung?token={token}"
    await build_mailer(settings).send(
        invitation_email(
            to=invitation.email,
            household_name=household.household.name,
            inviter=user.label,
            link=link,
        )
    )
    log.info(
        "invitation.created",
        extra={"household_id": household.id, "email": invitation.email},
    )
    return InvitationCreated(
        invitation=InvitationOut.model_validate(invitation),
        link=link,
        mail_sent=settings.mail_configured,
    )


@router.delete(
    "/active/invitations/{invitation_id}", status_code=status.HTTP_204_NO_CONTENT
)
async def revoke_invitation(
    session: SessionDep, household: HouseholdAdminDep, invitation_id: int
) -> None:
    invitation = await households_service.get_invitation(session, invitation_id)
    if invitation is None or invitation.household_id != household.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Einladung nicht gefunden."
        )
    await households_service.revoke_invitation(session, invitation)
