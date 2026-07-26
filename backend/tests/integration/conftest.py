"""Integration-test fixtures: real Postgres, app over an in-memory ASGI
transport, a captured mailer, and a pre-authenticated client."""

import os
import subprocess
from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa

from app.integrations.mail.sender import Email
from tests.conftest import BACKEND_DIR


class CapturingMailer:
    """Test mailer: keeps sent mail in memory so tests can read the login /
    invitation link (and its token)."""

    def __init__(self) -> None:
        self.sent: list[Email] = []

    async def send(self, email: Email) -> None:
        self.sent.append(email)

    def last_token(self, param: str = "token") -> str:
        assert self.sent, "no mail captured"
        for word in self.sent[-1].text.split():
            if word.startswith("http") and f"{param}=" in word:
                return word.split(f"{param}=", 1)[1]
        raise AssertionError(f"no {param}= link in mail: {self.sent[-1].text!r}")


@pytest.fixture(scope="session", autouse=True)
def _database() -> None:
    """Migrate + seed the test database once per integration test session."""
    env = os.environ.copy()
    subprocess.run(
        ["uv", "run", "alembic", "upgrade", "head"], cwd=BACKEND_DIR, env=env, check=True
    )
    subprocess.run(
        ["uv", "run", "python", "-m", "app.seed"], cwd=BACKEND_DIR, env=env, check=True
    )


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    """Pristine state before each test: no users/groups/receipts and the seeded
    category tree only. Deleting groups/users cascades all owned rows."""
    from redis.asyncio import Redis

    from app.core.config import get_settings
    from app.db.session import get_sessionmaker
    from app.seed import seed_categories

    async with get_sessionmaker()() as session:
        # groups cascade → members, invitations, receipts→line_items, items;
        # users cascade → refresh/magic tokens, oidc identities, memberships.
        await session.execute(sa.text("DELETE FROM groups"))
        await session.execute(sa.text("DELETE FROM users"))
        await session.execute(sa.text("DELETE FROM categories"))
        await session.commit()
        await seed_categories(session)

    # Reset rate-limit counters so tests are deterministic across runs.
    try:
        redis = Redis.from_url(get_settings().redis_url)
        await redis.flushdb()
        await redis.aclose()
    except Exception:
        pass
    yield


@pytest.fixture
async def mailer() -> AsyncIterator[CapturingMailer]:
    from app.integrations.mail import sender

    capturing = CapturingMailer()
    sender.set_mailer(capturing)
    yield capturing
    sender.set_mailer(None)


def _make_client(app: object) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.fixture
async def anon_client(_clean_state: None) -> AsyncIterator[httpx.AsyncClient]:
    """Unauthenticated client (for the auth flows themselves)."""
    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app), _make_client(app) as client:
        yield client


@pytest.fixture
async def second_client(_clean_state: None) -> AsyncIterator[httpx.AsyncClient]:
    """A second, independent unauthenticated client (own cookie jar) — models
    a different browser for the cross-browser pairing-code flow."""
    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app), _make_client(app) as client:
        yield client


@pytest.fixture
async def app_client(_clean_state: None) -> AsyncIterator[httpx.AsyncClient]:
    """Client pre-authenticated as an active admin of a fresh test group — the
    Authorization + X-Group-Id headers are set so existing endpoint tests just
    work."""
    from app.core.security import create_access_token
    from app.db.session import get_sessionmaker
    from app.main import create_app
    from app.services import auth_service, group_service

    async with get_sessionmaker()() as session:
        user = await auth_service.create_user(
            session, email="test@example.org", display_name="Test", is_instance_admin=True
        )
        await session.flush()
        group = await group_service.create_group(session, user=user, name="Testhaushalt")
        access = create_access_token(user.id, is_instance_admin=True)

    app = create_app()
    async with app.router.lifespan_context(app), _make_client(app) as client:
        client.headers["Authorization"] = f"Bearer {access}"
        client.headers["X-Group-Id"] = str(group.id)
        yield client
