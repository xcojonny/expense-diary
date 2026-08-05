"""Anwendungseinstieg — API **und** SPA aus einem Prozess (ADR-006).

Startablauf: Migrationen anwenden → Kategorien seeden → Worker starten. Damit
gibt es keinen `migrate`-Container und keine Reihenfolge beim Hochfahren.
"""

from __future__ import annotations

import contextlib
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import APIRouter, FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.requests import Request

from app.api.routes import (
    analytics,
    auth,
    categories,
    health,
    households,
    receipts,
    tokens,
)
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging, get_logger
from app.db.session import dispose_engine
from app.worker import Worker

log = get_logger(__name__)

# Die gebaute SPA. Im Container liegt sie hier; lokal fehlt sie, dann läuft der
# Vite-Dev-Server auf einem eigenen Port und proxyt /api hierher.
STATIC_DIR = Path(__file__).resolve().parent / "static"


async def _prepare_database(settings: Settings) -> None:
    """Migrationen und Seed — beim Start, nicht in einem eigenen Container."""
    import anyio
    from alembic.config import Config

    from alembic import command
    from app.db.session import get_sessionmaker
    from app.seed import seed_categories
    from app.services import users as users_service

    # Einmalig beim Start, vor dem ersten Request — synchron ist hier richtig.
    backend_dir = Path(__file__).resolve().parent.parent  # noqa: ASYNC240
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.sqlalchemy_url)
    # Unser Logging steht schon — Alembic soll es nicht überschreiben.
    config.attributes["configure_logger"] = False

    # Alembic ist synchron — im Thread laufen lassen, damit der Loop frei bleibt.
    await anyio.to_thread.run_sync(lambda: command.upgrade(config, "head"))
    log.info("db.migrated", extra={"url": settings.sqlalchemy_url.split("///")[-1]})

    async with get_sessionmaker()() as session:
        created = await seed_categories(session)
        # In den Einzelnutzer-Modi den impliziten Nutzer samt Haushalt anlegen;
        # in den Mehrbenutzer-Modi entstehen Nutzer beim ersten Login.
        await users_service.bootstrap(session, settings)
        await session.commit()
    if created:
        log.info("seed.categories_created", extra={"count": created})


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(settings.log_level, settings.log_format)

    @contextlib.asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        for problem in settings.validate_for_production():
            log.error("config.problem", extra={"detail": problem})
        # Einmal beim Start, bevor irgendwas läuft — synchron ist hier richtig.
        settings.data_dir.mkdir(parents=True, exist_ok=True)
        settings.media_dir.mkdir(parents=True, exist_ok=True)

        await _prepare_database(settings)

        worker = Worker(settings) if settings.worker_enabled else None
        if worker is not None:
            await worker.start()
        log.info(
            "app.started",
            extra={"auth_mode": settings.auth_mode.value, "llm": settings.llm_provider.value},
        )
        try:
            yield
        finally:
            if worker is not None:
                await worker.stop()
            await dispose_engine()

    app = FastAPI(
        title="Haushaltsbuch",
        version=health.VERSION,
        description="Kassenbon fotografieren, Ausgaben und Preistrends auswerten.",
        lifespan=lifespan,
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
    )

    api = APIRouter(prefix="/api")
    api.include_router(health.router)
    api.include_router(auth.router)
    api.include_router(households.router)
    api.include_router(receipts.router)
    api.include_router(categories.router)
    api.include_router(analytics.router)
    api.include_router(tokens.router)
    app.include_router(api)

    _mount_spa(app)
    return app


def _mount_spa(app: FastAPI) -> None:
    """Gebaute SPA ausliefern, inklusive Fallback für Client-Routen.

    Reihenfolge ist wichtig: die `/api`-Routen sind oben schon registriert und
    gewinnen; alles andere geht an die SPA. Ein unbekannter `/api`-Pfad darf
    **nicht** in `index.html` laufen, sonst bekäme ein API-Client HTML statt 404.
    """
    if not STATIC_DIR.is_dir():
        log.info("spa.not_bundled", extra={"path": str(STATIC_DIR)})
        return

    assets = STATIC_DIR / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="assets")

    index_file = STATIC_DIR / "index.html"

    # `response_model=None`: FastAPI würde sonst versuchen, aus dem
    # Rückgabetyp ein Antwort-Schema abzuleiten, und scheitert an der Union.
    @app.get("/{path:path}", include_in_schema=False, response_model=None)
    async def spa(request: Request, path: str) -> FileResponse | JSONResponse:
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)

        candidate = (STATIC_DIR / path).resolve()
        if (
            path
            and candidate.is_file()
            and candidate.is_relative_to(STATIC_DIR.resolve())
        ):
            return FileResponse(candidate)
        return FileResponse(index_file)


app = create_app()
