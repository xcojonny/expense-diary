from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from redis.asyncio import Redis

from app.api.deps import get_current_user
from app.api.v1 import analytics, auth, categories, groups, health, me, receipts, tokens
from app.core.config import get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import get_sessionmaker
from app.services import auth_service

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging()
    # media_dir is created synchronously in create_app().

    async with get_sessionmaker()() as session:
        await auth_service.ensure_initial_admin(session)

    # ARQ pool for enqueuing extraction jobs. If Redis is unreachable we degrade
    # gracefully: the upload endpoint falls back to FastAPI BackgroundTasks, so
    # the app still runs (and tests don't require Redis).
    app.state.arq = None
    try:
        app.state.arq = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    except Exception as exc:
        log.warning("ARQ pool unavailable — using in-process BackgroundTasks", error=str(exc))

    # Plain Redis for rate limiting. None ⇒ the limiter fails open.
    app.state.redis = None
    try:
        app.state.redis = Redis.from_url(settings.redis_url)
        await app.state.redis.ping()
    except Exception as exc:
        app.state.redis = None
        log.warning("Redis unavailable — rate limiting disabled", error=str(exc))

    log.info("startup complete", env=settings.app_env, arq=app.state.arq is not None)
    try:
        yield
    finally:
        if app.state.arq is not None:
            await app.state.arq.aclose()
        if app.state.redis is not None:
            await app.state.redis.aclose()


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
            allow_origins=[settings.base_url, "http://localhost:3010", "http://localhost:3000"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    api = "/api/v1"
    # Public: health + auth (login/refresh/OIDC).
    app.include_router(health.router, prefix=api)
    app.include_router(auth.router, prefix=api)
    # Authenticated. Group-owned routers enforce auth via get_current_group_id;
    # the rest carry an explicit get_current_user dependency.
    protected = [Depends(get_current_user)]
    app.include_router(me.router, prefix=api)
    app.include_router(tokens.router, prefix=api, dependencies=protected)
    app.include_router(groups.router, prefix=api)
    app.include_router(receipts.router, prefix=api)
    app.include_router(categories.router, prefix=api, dependencies=protected)
    app.include_router(analytics.router, prefix=api)

    media_dir = Path(settings.media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=str(media_dir)), name="media")

    return app


app = create_app()
