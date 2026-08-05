"""Mailversand für Einladungen — stdlib `smtplib`, keine Abhängigkeit.

Ohne `SMTP_HOST` wird der Link **geloggt** statt versendet. Das ist der
Dev-Modus und gleichzeitig der ehrliche Fallback: eine Einladung, die niemand
verschicken kann, soll nicht spurlos verschwinden.
"""

from __future__ import annotations

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

import anyio

from app.core.config import Settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(frozen=True)
class Email:
    to: str
    subject: str
    body: str


class Mailer:
    """Verschickt Mails oder loggt sie. Tests injizieren einen eigenen Mailer."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    async def send(self, email: Email) -> None:
        if not self._settings.mail_configured:
            # Kein SMTP: Link ins Log, damit man ihn trotzdem weitergeben kann.
            log.warning(
                "mail.not_configured",
                extra={"to": email.to, "subject": email.subject, "body": email.body},
            )
            return

        message = EmailMessage()
        message["From"] = self._settings.smtp_from
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.body)

        # smtplib ist synchron — in einen Thread, damit der Loop frei bleibt.
        await anyio.to_thread.run_sync(lambda: self._deliver(message))
        log.info("mail.sent", extra={"to": email.to})

    def _deliver(self, message: EmailMessage) -> None:
        settings = self._settings
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=20) as smtp:
            if settings.smtp_starttls:
                smtp.starttls()
            if settings.smtp_user:
                smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.send_message(message)


# Testeinstiegspunkt, analog zum LLM-Adapter.
_override: Mailer | None = None


def set_mailer(mailer: Mailer | None) -> None:
    global _override
    _override = mailer


def build_mailer(settings: Settings) -> Mailer:
    return _override if _override is not None else Mailer(settings)


def invitation_email(*, to: str, household_name: str, inviter: str, link: str) -> Email:
    return Email(
        to=to,
        subject=f"Einladung zum Haushaltsbuch „{household_name}“",
        body=(
            f"{inviter} hat dich zum Haushalt „{household_name}“ im Haushaltsbuch "
            f"eingeladen.\n\n"
            f"Zum Beitreten diesen Link öffnen:\n{link}\n\n"
            f"Der Link ist einmalig verwendbar und läuft nach einigen Tagen ab.\n"
        ),
    )
