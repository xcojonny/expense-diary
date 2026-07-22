"""Integration-test fixtures: real Postgres, app over an in-memory ASGI transport."""

import os
import subprocess
from collections.abc import AsyncIterator

import httpx
import pytest
import sqlalchemy as sa

from tests.conftest import BACKEND_DIR


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


@pytest.fixture
async def app_client() -> AsyncIterator[httpx.AsyncClient]:
    from app.main import create_app

    app = create_app()
    async with app.router.lifespan_context(app):
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            yield client


@pytest.fixture(autouse=True)
async def _clean_state() -> AsyncIterator[None]:
    """Fresh receipts per test; seeded master data (categories) stays."""
    yield
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        # line_items cascade from receipts (FK ON DELETE CASCADE); items are
        # top-level trend anchors not reachable by cascade, so clear them too.
        await session.execute(sa.text("DELETE FROM receipts"))
        await session.execute(sa.text("DELETE FROM items"))
        await session.commit()
