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
    """Reset to a pristine state *before* each test: no receipts/items and the
    seeded category tree only. Categories are reset too (not just left alone)
    because phase-5 tests mutate that master data — otherwise created/renamed
    categories would leak across tests and re-runs."""
    from app.db.session import get_sessionmaker
    from app.seed import seed_categories

    async with get_sessionmaker()() as session:
        # line_items cascade from receipts (FK ON DELETE CASCADE); items and
        # categories aren't reachable by that cascade, so clear them explicitly.
        await session.execute(sa.text("DELETE FROM receipts"))
        await session.execute(sa.text("DELETE FROM items"))
        await session.execute(sa.text("DELETE FROM categories"))
        await session.commit()
        await seed_categories(session)  # restore the pristine seed tree
    yield
