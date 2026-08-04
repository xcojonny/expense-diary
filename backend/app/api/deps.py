"""Abhängigkeiten — und die **einzige** Stelle, an der eine Identität entsteht.

Wer Mehrbenutzerbetrieb nachrüsten will, fängt hier an (ADR-004).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import AuthMode, Settings, get_settings
from app.core.security import read_session_token
from app.db.session import session_scope
from app.integrations.files import FileStore
from app.services import tokens as tokens_service

SessionDep = Annotated[AsyncSession, Depends(session_scope)]
SettingsDep = Annotated[Settings, Depends(get_settings)]


def get_file_store(settings: SettingsDep) -> FileStore:
    return FileStore(settings.media_dir)


FileStoreDep = Annotated[FileStore, Depends(get_file_store)]


async def require_auth(
    request: Request, settings: SettingsDep, session: SessionDep
) -> str:
    """Identität feststellen; wirft 401, wenn keine vorliegt.

    Drei Wege, in dieser Reihenfolge:

    1. **API-Token** im `Authorization: Bearer`-Header — für den iOS-Kurzbefehl.
    2. **Session-Cookie** aus dem Passwort-Login.
    3. **Vertrauter Header** vom Reverse Proxy (nur in `AUTH_MODE=trusted_header`).
    """
    if settings.auth_mode is AuthMode.NONE:
        return "anonymous"

    authorization = request.headers.get("Authorization", "")
    if authorization.startswith("Bearer "):
        token = await tokens_service.resolve(session, authorization[7:].strip())
        if token is not None:
            return f"token:{token.name}"

    if settings.auth_mode is AuthMode.TRUSTED_HEADER:
        # Sicher nur, wenn der Proxy diesen Header überschreibt — sonst kann ihn
        # jeder Client selbst mitschicken. Steht so in .env.example und README.
        user = request.headers.get(settings.auth_trusted_header, "").strip()
        if user:
            return user
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Header {settings.auth_trusted_header} fehlt.",
        )

    cookie = request.cookies.get(settings.cookie_name)
    if cookie:
        subject = read_session_token(cookie, secret=settings.session_secret)
        if subject is not None:
            return subject

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Nicht angemeldet.")


AuthDep = Annotated[str, Depends(require_auth)]
