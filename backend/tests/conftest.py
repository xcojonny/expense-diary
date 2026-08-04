"""Test-Fixtures — ohne Postgres, ohne Redis, ohne Portannahmen (ADR-010).

Zwei Lehren aus dem Altstand stecken hier drin:

1. Die Umgebung wird **explizit gesetzt**, nicht per `setdefault`. Vorher
   entschied ein `.env` oder eine Shell-Variable mit, gegen welchen Redis-Port
   die Tests laufen — und genau daran scheiterte `make check`.
2. Der Kategorien-Seed läuft **einmal pro Session**, nicht vor jedem Test. Das
   `autouse`-Fixture räumt nur die Bewegungsdaten weg.
"""

from __future__ import annotations

import os
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path

# MUSS vor jedem app-Import stehen — Settings sind gecacht.
_TMP = Path(tempfile.mkdtemp(prefix="expense-test-"))
TEST_PASSWORD = "test-passwort"

os.environ["APP_ENV"] = "test"
os.environ["DATA_DIR"] = str(_TMP)
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(_TMP / 'test.db').as_posix()}"
os.environ["SECRET_KEY"] = "test-secret-mindestens-32-zeichen-lang-0123456789"
os.environ["AUTH_MODE"] = "password"
os.environ["AUTH_PASSWORD"] = TEST_PASSWORD
os.environ["COOKIE_SECURE"] = "false"
os.environ["LLM_PROVIDER"] = "none"
os.environ["LOG_LEVEL"] = "WARNING"
# Die Tests treiben die Queue selbst (`drain_jobs`) — deterministisch statt
# gegen eine Hintergrundschleife zu rennen.
os.environ["WORKER_ENABLED"] = "false"

import httpx  # noqa: E402
import pytest  # noqa: E402
import sqlalchemy as sa  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from sqlalchemy.ext.asyncio import AsyncSession  # noqa: E402

from app.api.routes import auth as auth_routes  # noqa: E402
from app.core.config import get_settings  # noqa: E402
from app.db.session import get_sessionmaker  # noqa: E402
from app.integrations.llm import set_vision_model  # noqa: E402

# Bewegungsdaten; `categories` bleibt stehen (einmal geseedet).
_MUTABLE_TABLES = ("jobs", "line_items", "receipts", "items", "api_tokens")


@pytest.fixture(scope="session")
def settings() -> object:
    return get_settings()


@pytest.fixture(scope="session")
async def app() -> AsyncIterator[FastAPI]:
    """Die App **einmal** pro Session — der Lifespan migriert und seedet."""
    from app.main import create_app

    application = create_app()
    async with application.router.lifespan_context(application):
        yield application


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    """Bewegungsdaten leeren, Modell-Override und Login-Limit zurücksetzen."""
    set_vision_model(None)
    auth_routes.reset_login_limiter()
    async with get_sessionmaker()() as session:
        for table in _MUTABLE_TABLES:
            await session.execute(sa.text(f"DELETE FROM {table}"))
        await session.commit()
    yield


@pytest.fixture
async def db() -> AsyncIterator[AsyncSession]:
    async with get_sessionmaker()() as session:
        yield session


def _build_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://testserver"
    )


@pytest.fixture
async def anon_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Nicht angemeldeter Client."""
    async with _build_client(app) as client:
        yield client


@pytest.fixture
async def second_client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    """Ein **eigener** Client mit eigenem Cookie-Jar.

    Wichtig: `client` ist dasselbe Objekt wie `anon_client` (es baut darauf auf).
    Wer „angemeldet vs. nicht angemeldet" gegeneinander testen will, braucht
    diesen hier.
    """
    async with _build_client(app) as client:
        yield client


@pytest.fixture
async def client(anon_client: httpx.AsyncClient) -> AsyncIterator[httpx.AsyncClient]:
    """Angemeldeter Client — das Session-Cookie liegt im Cookie-Jar."""
    response = await anon_client.post("/api/auth/login", json={"password": TEST_PASSWORD})
    assert response.status_code == 200, response.text
    yield anon_client


async def drain_jobs() -> int:
    """Offene Extraktionsjobs jetzt abarbeiten (statt auf den Worker zu warten)."""
    from app.worker import run_pending_jobs

    return await run_pending_jobs(get_settings())


class FakeVisionModel:
    """Vision-Adapter-Attrappe: liefert eine vorgegebene Antwort oder wirft."""

    def __init__(self, response: str | None = None, error: Exception | None = None) -> None:
        self._response = response
        self._error = error
        self.calls = 0

    name = "fake"
    available = True

    async def extract(self, *, image: bytes, media_type: str, prompt: str) -> str | None:
        self.calls += 1
        if self._error is not None:
            raise self._error
        return self._response


# --- Testdaten ----------------------------------------------------------------

# 1×1-PNG — kleinstes gültiges Bild, das die Magic-Byte-Prüfung besteht.
PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4949484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001"
    "0d0a2db40000000049454e44ae426082"
)


def make_text_pdf(lines: list[str]) -> bytes:
    """Minimales Text-PDF mit den gegebenen Zeilen.

    Bewusst handgebaut statt mit reportlab: der Test soll den **echten**
    eBon-Pfad prüfen (pypdf zieht Text, der Parser interpretiert ihn), ohne dafür
    eine Abhängigkeit mitzuschleppen.
    """

    def escape(text: str) -> str:
        return text.replace("\\", r"\\").replace("(", r"\(").replace(")", r"\)")

    body = "BT\n/F1 10 Tf\n20 760 Td\n12 TL\n"
    body += "".join(f"({escape(line)}) Tj T*\n" for line in lines)
    body += "ET"
    stream = body.encode("latin-1", errors="replace")

    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 400 800] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(stream)).encode() + b" >>\nstream\n" + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Courier >>",
    ]

    out = bytearray(b"%PDF-1.4\n")
    offsets: list[int] = []
    for number, payload in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{number} 0 obj\n".encode() + payload + b"\nendobj\n"

    xref_at = len(out)
    out += f"xref\n0 {len(objects) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for offset in offsets:
        out += f"{offset:010d} 00000 n \n".encode()
    out += (
        f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF\n"
    ).encode()
    return bytes(out)


REWE_RECEIPT_LINES = [
    "R E W E",
    "www.rewe.de",
    "H-MILCH 3,5%             1,09 B",
    "BUTTER MILDGES.          2,49 B",
    "BANANEN                  1,38 B",
    "0,780 kg x 1,77",
    "PFAND 0,25               0,25 A",
    "RABATT AKTION           -0,50 B",
    "SUMME                    4,71",
    "Geg. BAR                 5,00",
    "04.03.2026  17:42",
]
