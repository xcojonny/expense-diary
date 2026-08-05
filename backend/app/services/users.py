"""Nutzer anlegen, finden und beim Start bootstrappen.

Es gibt keine Passwortspalte (ADR-004): ein Nutzer entsteht über OIDC, über den
vertrauten Proxy-Header oder — in den Einzelnutzer-Modi — als der eine implizite
Haushaltsnutzer.
"""

from __future__ import annotations

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.logging import get_logger
from app.models import Household, HouseholdMember, OidcIdentity, Role, User
from app.services import households as households_service

log = get_logger(__name__)

# Der implizite Nutzer der Einzelnutzer-Modi (`password`, `none`). Eine feste
# Adresse, damit ein späterer Wechsel auf OIDC dieselben Daten wiederfindet.
SINGLE_USER_EMAIL = "haushalt@localhost"
DEFAULT_HOUSEHOLD_NAME = "Haushalt"


async def get(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    return (
        await session.execute(sa.select(User).where(User.email == email.strip().lower()))
    ).scalar_one_or_none()


async def create(
    session: AsyncSession, *, email: str, display_name: str = "", is_active: bool = True
) -> User:
    user = User(
        email=email.strip().lower(), display_name=display_name.strip(), is_active=is_active
    )
    session.add(user)
    await session.flush()
    return user


async def get_or_create_by_email(
    session: AsyncSession, *, email: str, display_name: str = ""
) -> User:
    user = await get_by_email(session, email)
    if user is not None:
        # Anzeigename nachtragen, wenn er beim Anlegen fehlte.
        if not user.display_name and display_name:
            user.display_name = display_name.strip()
        return user
    return await create(session, email=email, display_name=display_name)


async def upsert_oidc_user(
    session: AsyncSession, *, issuer: str, subject: str, email: str, display_name: str
) -> User:
    """`(issuer, subject)` → Nutzer. Der Abgleich läuft über `subject`.

    Fällt der Abgleich leer aus, wird nach E-Mail gesucht: so übernimmt ein
    bestehender Datensatz (etwa aus einer Einladung) die OIDC-Identität statt
    einen Zwilling anzulegen.
    """
    identity = (
        await session.execute(
            sa.select(OidcIdentity).where(
                OidcIdentity.issuer == issuer, OidcIdentity.subject == subject
            )
        )
    ).scalar_one_or_none()

    if identity is not None:
        user = await session.get(User, identity.user_id)
        if user is None:  # verwaiste Identität — kann nur bei manuellem Eingriff sein
            raise ValueError("OIDC-Identität verweist auf einen gelöschten Nutzer.")
        if email and user.email != email.strip().lower():
            user.email = email.strip().lower()
        if display_name and not user.display_name:
            user.display_name = display_name.strip()
        return user

    if not email:
        raise ValueError(
            "Der Identity Provider hat keine E-Mail-Adresse geliefert — "
            "der Scope 'email' fehlt vermutlich."
        )

    user = await get_or_create_by_email(session, email=email, display_name=display_name)
    session.add(OidcIdentity(user_id=user.id, issuer=issuer, subject=subject))
    await session.flush()
    return user


async def ensure_personal_household(session: AsyncSession, user: User) -> Household:
    """Jeder Nutzer braucht einen Haushalt, sonst sieht er eine leere App.

    Wer über eine Einladung kommt, hat schon eine Mitgliedschaft und bekommt
    keinen zweiten Haushalt.
    """
    existing = (
        await session.execute(
            sa.select(HouseholdMember).where(HouseholdMember.user_id == user.id).limit(1)
        )
    ).scalar_one_or_none()
    if existing is not None:
        household = await session.get(Household, existing.household_id)
        if household is not None:
            return household

    name = f"Haushalt {user.display_name or user.email}".strip()
    household = await households_service.create(session, name=name, owner=user)
    log.info("household.created", extra={"household_id": household.id, "user_id": user.id})
    return household


async def ensure_single_user(session: AsyncSession, settings: Settings) -> User:
    """Den impliziten Nutzer der Modi `password`/`none` bereitstellen."""
    user = await get_by_email(session, SINGLE_USER_EMAIL)
    if user is None:
        user = await create(session, email=SINGLE_USER_EMAIL, display_name="Haushalt")
    if not await households_service.memberships_for(session, user.id):
        household = Household(name=DEFAULT_HOUSEHOLD_NAME)
        session.add(household)
        await session.flush()
        session.add(
            HouseholdMember(
                household_id=household.id, user_id=user.id, role=Role.ADMIN.value
            )
        )
        await session.flush()
    return user


async def bootstrap(session: AsyncSession, settings: Settings) -> None:
    """Beim Start: in Einzelnutzer-Modi den impliziten Nutzer sicherstellen.

    In den Mehrbenutzer-Modi passiert hier nichts — Nutzer entstehen beim ersten
    Login.
    """
    if settings.auth_mode.is_multi_user:
        return
    await ensure_single_user(session, settings)
