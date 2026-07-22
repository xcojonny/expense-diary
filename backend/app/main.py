from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import analytics, categories, health, receipts
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_sessionmaker
from app.services import group_service

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    # media_dir is created synchronously in create_app().

    async with get_sessionmaker()() as session:
        await group_service.ensure_default_group(session)

    # ARQ pool for enqueuing extraction jobs. If Redis is unreachable we degrade
    # gracefully: the upload endpoint falls back to FastAPI BackgroundTasks, so
    # the app still runs (and tests don't require Redis).
    app.state.arq = None
    try:
        app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception as exc:
        log.warning("ARQ pool unavailable — using in-process BackgroundTasks", error=str(exc))

    log.info("startup complete", env=settings.app_env, arq=app.state.arq is not None)
    try:
        yield
    finally:
        if app.state.arq is not None:
            await app.state.arq.aclose()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Expense Diary API",
        version="0.1.0",
        description="Selbst gehostetes, KI-gestütztes Haushaltsbuch",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.is_dev else None,
        openapi_url="/api/openapi.json",
    )

    if settings.is_dev:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=[settings.base_url, "http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    api = "/api/v1"
    app.include_router(health.router, prefix=api)
    app.include_router(receipts.router, prefix=api)
    app.include_router(categories.router, prefix=api)
    app.include_router(analytics.router, prefix=api)

    media_dir = Path(settings.media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

    return app


app = create_app()
