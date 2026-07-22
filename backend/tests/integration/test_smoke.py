import httpx
import pytest
from sqlalchemy import func, select

pytestmark = pytest.mark.integration


async def test_healthz(app_client: httpx.AsyncClient) -> None:
    response = await app_client.get("/api/v1/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_readyz_reaches_db(app_client: httpx.AsyncClient) -> None:
    response = await app_client.get("/api/v1/readyz")
    assert response.status_code == 200
    assert response.json() == {"status": "ready"}


async def test_categories_are_seeded() -> None:
    """The seed ran (session fixture): the category tree exists with a
    working parent/child hierarchy."""
    from app.db.session import get_sessionmaker
    from app.models import Category

    async with get_sessionmaker()() as session:
        total = (await session.execute(select(func.count()).select_from(Category))).scalar_one()
        assert total >= 17  # 17 top-level + a few sub-categories

        # "Käse" hangs under "Milchprodukte & Eier".
        kaese = (
            await session.execute(select(Category).where(Category.name == "Käse"))
        ).scalar_one()
        parent = (
            await session.execute(select(Category).where(Category.id == kaese.parent_id))
        ).scalar_one()
        assert parent.name == "Milchprodukte & Eier"
