"""Outgoing mail for magic-link logins and group invitations.

With no SMTP host configured the mailer just logs the message (the login link
is visible in the backend log) — enough for local dev. Tests install a
capturing mailer via ``set_mailer``.
"""

from dataclasses import dataclass
from email.message import EmailMessage
from typing import Protocol

import aiosmtplib

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass
class Email:
    to: str
    subject: str
    text: str


class Mailer(Protocol):
    async def send(self, email: Email) -> None: ...


class LoggingMailer:
    """Dev fallback: logs instead of sending, so links are grabbable from logs."""

    async def send(self, email: Email) -> None:
        log.info("mail (not sent — no SMTP configured)", to=email.to, subject=email.subject,
                 body=email.text)


class SmtpMailer:
    async def send(self, email: Email) -> None:
        settings = get_settings()
        message = EmailMessage()
        message["From"] = f"{settings.mail_from_name} <{settings.mail_from}>"
        message["To"] = email.to
        message["Subject"] = email.subject
        message.set_content(email.text)
        await aiosmtplib.send(
            message,
            hostname=settings.smtp_host,
            port=settings.smtp_port,
            username=settings.smtp_user or None,
            password=settings.smtp_password or None,
            start_tls=settings.smtp_starttls,
        )


_override: Mailer | None = None


def set_mailer(mailer: Mailer | None) -> None:
    """Install (or clear) a mailer override — used by tests to capture mail."""
    global _override
    _override = mailer


def get_mailer() -> Mailer:
    if _override is not None:
        return _override
    return SmtpMailer() if get_settings().smtp_host else LoggingMailer()


async def send_mail(email: Email) -> None:
    await get_mailer().send(email)
