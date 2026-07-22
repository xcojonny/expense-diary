from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1 import health
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    # media_dir is created synchronously in create_app(); nothing async to set
    # up yet (Redis/ARQ arrive with the extraction worker in step 2).
    log.info("startup complete", env=settings.app_env)
    yield


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
    # Receipts, categories and the analytics endpoints mount here in later steps.

    media_dir = Path(settings.media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

    return app


app = create_app()
