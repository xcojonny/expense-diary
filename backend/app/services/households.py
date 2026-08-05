"""Haushalte, Mitgliedschaften, Einladungen.

Regeln, die die Datenbank allein nicht durchsetzt:

* Ein Haushalt behält **mindestens einen Admin** — der letzte kann sich nicht
  selbst entfernen oder herabstufen, sonst wäre der Haushalt verwaltungslos.
* Einladungen sind einmalig verwendbar und laufen ab.
* Einladungen gibt es nur in mehrbenutzerfähigen Auth-Modi — in `password`
  könnte der eingeladene Mensch sich nicht anmelden (ADR-004).
"""

from __future__ import annotations

import secrets
from datetime import timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.security import hash_api_token
from app.db.base import utcnow
from app.models import Household, HouseholdMember, Invitation, Role, User

INVITE_TOKEN_BYTES = 32


class HouseholdError(ValueError):
    """Fachlicher Konflikt (fehlende Rechte, letzter Admin, ungültige Einladung)."""


# --- Haushalte ----------------------------------------------------------------


async def create(session: AsyncSession, *, name: str, owner: User) -> Household:
    """Haushalt anlegen; der Ersteller wird Admin."""
    cleaned = name.strip()
    if not cleaned:
        raise HouseholdError("Der Name darf nicht leer sein.")

    household = Household(name=cleaned)
    session.add(household)
    await session.flush()

    session.add(
        HouseholdMember(household_id=household.id, user_id=owner.id, role=Role.ADMIN.value)
    )
    await session.flush()
    return household


async def get(session: AsyncSession, household_id: int) -> Household | None:
    return await session.get(Household, household_id)


async def rename(session: AsyncSession, household: Household, *, name: str) -> Household:
    cleaned = name.strip()
    if not cleaned:
        raise HouseholdError("Der Name darf nicht leer sein.")
    household.name = cleaned
    await session.flush()
    return household


async def list_for_user(session: AsyncSession, user: User) -> list[Household]:
    rows = (
        await session.execute(
            sa.select(Household)
            .join(HouseholdMember, HouseholdMember.household_id == Household.id)
            .where(HouseholdMember.user_id == user.id)
            .order_by(Household.id)
        )
    ).scalars()
    return list(rows)


async def membership(
    session: AsyncSession, *, household_id: int, user_id: int
) -> HouseholdMember | None:
    return (
        await session.execute(
            sa.select(HouseholdMember).where(
                HouseholdMember.household_id == household_id,
                HouseholdMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()


async def memberships_for(session: AsyncSession, user_id: int) -> list[HouseholdMember]:
    """Mitgliedschaften eines Nutzers, Haushalt mitgeladen.

    Bewusst eine Abfrage statt `user.memberships`: bei einem gerade angelegten
    Nutzer gilt die Collection als ungeladen, und der Zugriff wäre ein
    Lazy-Load im async-Pfad (MissingGreenlet).
    """
    rows = (
        await session.execute(
            sa.select(HouseholdMember)
            .where(HouseholdMember.user_id == user_id)
            .options(selectinload(HouseholdMember.household))
            .order_by(HouseholdMember.id)
        )
    ).scalars()
    return list(rows)


async def members(session: AsyncSession, household_id: int) -> list[HouseholdMember]:
    """Mitglieder samt Nutzerdaten — `user` ist hier ausdrücklich mitgeladen,
    weil die Relation lazy ist (siehe models/household.py)."""
    rows = (
        await session.execute(
            sa.select(HouseholdMember)
            .where(HouseholdMember.household_id == household_id)
            .options(selectinload(HouseholdMember.user))
            .order_by(HouseholdMember.id)
        )
    ).scalars()
    return list(rows)


async def _count_admins(session: AsyncSession, household_id: int) -> int:
    return (
        await session.execute(
            sa.select(sa.func.count(HouseholdMember.id)).where(
                HouseholdMember.household_id == household_id,
                HouseholdMember.role == Role.ADMIN.value,
            )
        )
    ).scalar_one()


async def set_role(
    session: AsyncSession, member: HouseholdMember, *, role: str
) -> HouseholdMember:
    if role not in (Role.ADMIN.value, Role.MEMBER.value):
        raise HouseholdError(f"Unbekannte Rolle: {role}")
    if (
        member.role == Role.ADMIN.value
        and role != Role.ADMIN.value
        and await _count_admins(session, member.household_id) <= 1
    ):
        raise HouseholdError("Der letzte Admin kann sich nicht herabstufen.")
    member.role = role
    await session.flush()
    return member


async def remove_member(session: AsyncSession, member: HouseholdMember) -> None:
    """Mitglied entfernen. Die Bons des Haushalts bleiben — sie gehören dem
    Haushalt, nicht der Person."""
    if (
        member.role == Role.ADMIN.value
        and await _count_admins(session, member.household_id) <= 1
    ):
        raise HouseholdError(
            "Der letzte Admin kann nicht entfernt werden. Erst jemand anderen zum "
            "Admin machen oder den Haushalt löschen."
        )
    await session.delete(member)
    await session.flush()


async def delete(session: AsyncSession, household: Household) -> None:
    """Haushalt löschen — **inklusive** seiner Bons und Artikel (FK-Kaskade)."""
    await session.delete(household)
    await session.flush()


# --- Einladungen --------------------------------------------------------------


async def create_invitation(
    session: AsyncSession,
    *,
    household: Household,
    email: str,
    role: str,
    invited_by: User,
    ttl_hours: int,
) -> tuple[Invitation, str]:
    """`(datensatz, klartext-token)`. Der Klartext steht nur im Einladungslink."""
    cleaned = email.strip().lower()
    if "@" not in cleaned:
        raise HouseholdError("Bitte eine E-Mail-Adresse angeben.")
    if role not in (Role.ADMIN.value, Role.MEMBER.value):
        raise HouseholdError(f"Unbekannte Rolle: {role}")

    existing = await session.execute(
        sa.select(User.id)
        .join(HouseholdMember, HouseholdMember.user_id == User.id)
        .where(User.email == cleaned, HouseholdMember.household_id == household.id)
    )
    if existing.first() is not None:
        raise HouseholdError(f"{cleaned} ist bereits Mitglied dieses Haushalts.")

    plain = secrets.token_urlsafe(INVITE_TOKEN_BYTES)
    invitation = Invitation(
        household_id=household.id,
        email=cleaned,
        role=role,
        token_hash=hash_api_token(plain),
        invited_by_user_id=invited_by.id,
        expires_at=utcnow() + timedelta(hours=ttl_hours),
    )
    session.add(invitation)
    await session.flush()
    return invitation, plain


async def open_invitations(session: AsyncSession, household_id: int) -> list[Invitation]:
    rows = (
        await session.execute(
            sa.select(Invitation)
            .where(
                Invitation.household_id == household_id,
                Invitation.accepted_at.is_(None),
                Invitation.expires_at > utcnow(),
            )
            .order_by(Invitation.id)
        )
    ).scalars()
    return list(rows)


async def get_invitation(session: AsyncSession, invitation_id: int) -> Invitation | None:
    return await session.get(Invitation, invitation_id)


async def revoke_invitation(session: AsyncSession, invitation: Invitation) -> None:
    await session.delete(invitation)
    await session.flush()


async def accept_invitation(
    session: AsyncSession, *, token: str, user: User
) -> HouseholdMember:
    """Einladung einlösen und den **angemeldeten** Nutzer aufnehmen.

    Der Token ist die Berechtigung, nicht die E-Mail-Adresse: wer den Link hat,
    darf beitreten. Das ist bewusst so, damit ein Beitritt nicht daran scheitert,
    dass der Identity Provider eine andere Mailadresse liefert als die, an die
    eingeladen wurde.
    """
    invitation = (
        await session.execute(
            sa.select(Invitation).where(Invitation.token_hash == hash_api_token(token))
        )
    ).scalar_one_or_none()

    if invitation is None:
        raise HouseholdError("Diese Einladung ist unbekannt.")
    if invitation.accepted_at is not None:
        raise HouseholdError("Diese Einladung wurde schon eingelöst.")
    if invitation.expires_at <= utcnow():
        raise HouseholdError("Diese Einladung ist abgelaufen.")

    existing = await membership(
        session, household_id=invitation.household_id, user_id=user.id
    )
    if existing is not None:
        # Kein Fehler: der Effekt ist schon eingetreten. Token verbrauchen und fertig.
        invitation.accepted_at = utcnow()
        await session.flush()
        return existing

    member = HouseholdMember(
        household_id=invitation.household_id, user_id=user.id, role=invitation.role
    )
    session.add(member)
    invitation.accepted_at = utcnow()
    await session.flush()
    return member
