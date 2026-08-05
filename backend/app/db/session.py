"""Engine und Session.

Die beiden SQLite-spezifischen Stellen des Projekts sind hier gebündelt und
markiert (ADR-001) — wer auf Postgres zurückwill, fängt hier an.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _configure_sqlite(engine: AsyncEngine) -> None:
    """SQLite-spezifisch (ADR-001): Pragmas gelten **pro Verbindung**.

    `foreign_keys=ON` ist nicht optional — ohne das Pragma ignoriert SQLite
    jeden Fremdschlüssel, und `ON DELETE CASCADE` an `line_items` würde
    schlicht nichts tun.
    """

    @sa.event.listens_for(engine.sync_engine, "connect")
    def _pragmas(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")  # gleichzeitiges Lesen + Schreiben
        cursor.execute("PRAGMA synchronous=NORMAL")  # WAL-sicher, deutlich schneller
        cursor.execute("PRAGMA busy_timeout=5000")  # statt sofort "database is locked"
        cursor.close()


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        settings = get_settings()
        url = settings.sqlalchemy_url
        if url.startswith("sqlite"):
            # Verzeichnis anlegen, sonst schlägt der erste Connect fehl.
            path = url.split("///", 1)[-1]
            if path and path != ":memory:":
                Path(path).parent.mkdir(parents=True, exist_ok=True)
        _engine = create_async_engine(url, echo=False, future=True)
        if _engine.dialect.name == "sqlite":
            _configure_sqlite(_engine)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(
            get_engine(), expire_on_commit=False, autoflush=False
        )
    return _sessionmaker


async def session_scope() -> AsyncIterator[AsyncSession]:
    """FastAPI-Dependency: eine Session pro Request, Commit am Ende."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None
