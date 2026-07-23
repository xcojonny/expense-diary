"""Browser-bound magic-link login with cross-browser pairing codes.

A login link only starts a session in the browser that requested it (matching
the ``login_request`` cookie secret). Opened elsewhere it reveals a short
pairing code — useless without that browser's cookie — which the user types
into the original browser (Claude.ai-style). This defeats login-by-forwarded-link.
"""

import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.ratelimit import RateLimiter
from app.core.security import generate_token, hash_token, login_code_for, matches_login_code
from app.integrations.mail.sender import Email, send_mail
from app.models import MagicLinkToken, User
from app.services import auth_service

log = get_logger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


class VerificationError(Exception):
    """User-visible verification failure."""


@dataclass
class VerifyResult:
    """Either a logged-in user, or a pairing code for the requesting browser."""

    user: User | None = None
    code: str | None = None


async def request_login_link(
    session: AsyncSession,
    limiter: RateLimiter,
    *,
    email: str,
    ip: str | None,
    requester_secret: str,
) -> None:
    """Create + email a browser-bound login link. Always a no-op from the
    caller's view (no account enumeration); rate-limited per email and IP."""
    settings = get_settings()
    email_ok = await limiter.hit(f"ml:email:{email.lower()}", settings.magic_link_per_email, 900)
    ip_ok = await limiter.hit(f"ml:ip:{ip or 'none'}", settings.magic_link_per_ip, 3600)
    if not (email_ok and ip_ok):
        # Logged (not surfaced) so a rate-limited address is diagnosable without
        # leaking to the caller — a frequent cause of "no mail arrives".
        log.warning("magic-link rate-limited", email=email, ip=ip, email_ok=email_ok, ip_ok=ip_ok)
        return

    user = await auth_service.get_user_by_email(session, email)
    if user is None or user.status != "active":
        log.info("magic-link: no active user for address", email=email)
        return

    raw = generate_token()
    session.add(
        MagicLinkToken(
            email=user.email,
            user_id=user.id,
            token_hash=hash_token(raw),
            expires_at=_now() + timedelta(minutes=settings.magic_link_ttl_minutes),
            request_ip=ip,
            requester_hash=hash_token(requester_secret),
        )
    )
    await session.commit()

    link = f"{settings.base_url}/login?token={raw}"
    binding_hint = (
        " Er funktioniert nur in dem Browser, in dem du ihn angefordert hast; öffnest "
        "du ihn woanders, zeigt die Seite einen kurzen Code."
        if settings.magic_link_require_same_browser
        else ""
    )
    try:
        await send_mail(
            Email(
                to=user.email,
                subject="Dein Anmeldelink fürs Haushaltsbuch",
                text=f"Hallo {user.display_name},\n\nmit diesem Link meldest du dich an:\n{link}"
                f"\n\nDer Link ist {settings.magic_link_ttl_minutes} Minuten gültig.{binding_hint}",
            )
        )
        log.info("magic-link mail sent", email=user.email)
    except Exception as exc:
        log.error("magic-link mail send FAILED", email=user.email, error=str(exc))


async def _consume(session: AsyncSession, raw: str) -> MagicLinkToken | None:
    """Atomic single-use redemption — the UPDATE…RETURNING wins any race."""
    token_id = (
        await session.execute(
            sa.update(MagicLinkToken)
            .where(
                MagicLinkToken.token_hash == hash_token(raw),
                MagicLinkToken.used_at.is_(None),
                MagicLinkToken.expires_at > _now(),
            )
            .values(used_at=_now())
            .returning(MagicLinkToken.id)
        )
    ).scalar_one_or_none()
    return await session.get(MagicLinkToken, token_id) if token_id else None


async def verify(
    session: AsyncSession, raw: str, *, requester_secret: str | None
) -> VerifyResult:
    """Redeem a login link. Bound browser → session; any other browser → pairing
    code to type into the requesting one (the mail never carries the code)."""
    settings = get_settings()
    token = (
        await session.execute(
            sa.select(MagicLinkToken).where(MagicLinkToken.token_hash == hash_token(raw))
        )
    ).scalar_one_or_none()
    if token is None or token.expires_at < _now() or token.requester_hash is None:
        raise VerificationError("Der Link ist ungültig oder abgelaufen.")

    bound_here = requester_secret is not None and hmac.compare_digest(
        hash_token(requester_secret), token.requester_hash
    )
    # When same-browser binding is relaxed (trusted homelab), a valid single-use
    # link logs in wherever it's opened — no pairing-code dance.
    if not bound_here and not settings.magic_link_require_same_browser:
        bound_here = True
    if not bound_here:
        if token.used_at is not None:
            raise VerificationError("Der Link wurde bereits verwendet.")
        token.opened_at = token.opened_at or _now()  # requesting browser's poll flips to "code"
        await session.commit()
        return VerifyResult(code=login_code_for(token.id))

    if await _consume(session, raw) is None:
        # A bound browser replaying its own just-used link (mail preview + real
        # open) within the grace window is the same user, not an attack.
        grace = timedelta(seconds=settings.magic_link_replay_grace_seconds)
        if not (token.used_at is not None and token.used_at > _now() - grace):
            raise VerificationError("Der Link ist ungültig oder abgelaufen.")

    user = await auth_service.get_user_by_email(session, token.email)
    if user is None or user.status != "active":
        raise VerificationError("Der Link ist ungültig oder abgelaufen.")
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    await session.commit()
    return VerifyResult(user=user)


async def login_status(session: AsyncSession, *, requester_secret: str) -> str:
    """What the requesting browser's poll may know about its newest link:
    `pending` | `code` (opened elsewhere → show the code form) | `used`
    (redeemed — a sibling tab can pick up the session via /auth/refresh).
    Answers `pending` for unknown cookies, so it leaks nothing."""
    token = (
        await session.execute(
            sa.select(MagicLinkToken)
            .where(
                MagicLinkToken.requester_hash == hash_token(requester_secret),
                MagicLinkToken.expires_at > _now(),
            )
            .order_by(MagicLinkToken.created_at.desc())
            .limit(1)
        )
    ).scalars().first()
    if token is None:
        return "pending"
    if token.used_at is not None:
        return "used"
    if token.opened_at is not None:
        return "code"
    return "pending"


async def verify_code(session: AsyncSession, *, code: str, requester_secret: str) -> User:
    """Finish a cross-browser login in the requesting browser: the pairing code
    only works together with this browser's cookie secret."""
    settings = get_settings()
    candidates = list(
        (
            await session.execute(
                sa.select(MagicLinkToken)
                .where(
                    MagicLinkToken.requester_hash == hash_token(requester_secret),
                    MagicLinkToken.used_at.is_(None),
                    MagicLinkToken.expires_at > _now(),
                    MagicLinkToken.code_attempts < settings.magic_link_code_attempts,
                )
                .order_by(MagicLinkToken.created_at.desc())
            )
        ).scalars()
    )
    matched = next((t for t in candidates if matches_login_code(code, t.id)), None)
    if matched is None:
        if candidates:  # burn an attempt on every open token of this browser
            await session.execute(
                sa.update(MagicLinkToken)
                .where(MagicLinkToken.id.in_([t.id for t in candidates]))
                .values(code_attempts=MagicLinkToken.code_attempts + 1)
            )
            await session.commit()
        raise VerificationError("Der Code ist ungültig oder abgelaufen.")

    claimed = (
        await session.execute(
            sa.update(MagicLinkToken)
            .where(MagicLinkToken.id == matched.id, MagicLinkToken.used_at.is_(None))
            .values(used_at=_now())
            .returning(MagicLinkToken.id)
        )
    ).scalar_one_or_none()
    if claimed is None:
        raise VerificationError("Der Code ist ungültig oder abgelaufen.")

    user = await auth_service.get_user_by_email(session, matched.email)
    if user is None or user.status != "active":
        raise VerificationError("Der Code ist ungültig oder abgelaufen.")
    if user.email_verified_at is None:
        user.email_verified_at = _now()
    await session.commit()
    return user
