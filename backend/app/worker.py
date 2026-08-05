"""Der Worker — ein asyncio-Task im API-Prozess (ADR-002).

Kein Redis, kein ARQ, kein zweiter Container. Die Schleife wartet auf ein
Event (ein Upload weckt sie sofort) und fällt nach `WORKER_IDLE_SECONDS` von
selbst wach, um Jobs mit abgelaufenem Backoff aufzunehmen.

Warum das den Prozess nicht blockiert: die Arbeit ist I/O — Datei lesen,
HTTP-Aufruf zum Modell, DB schreiben. Zwischen jedem `await` bedient derselbe
Loop weiter Requests.
"""

from __future__ import annotations

import asyncio
import contextlib

from app.core.config import Settings
from app.core.logging import get_logger
from app.db.session import get_sessionmaker
from app.integrations.files import FileStore
from app.integrations.llm import build_vision_model
from app.services import extraction as extraction_service
from app.services import jobs as jobs_service

log = get_logger(__name__)


class Worker:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()

    async def start(self) -> None:
        async with get_sessionmaker()() as session:
            await jobs_service.requeue_stale(session)
        self._task = asyncio.create_task(self._run(), name="extraction-worker")
        log.info("worker.started")

    async def stop(self) -> None:
        self._stopping.set()
        jobs_service.wake_worker()  # aus dem Warten holen
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        log.info("worker.stopped")

    async def _run(self) -> None:
        while not self._stopping.is_set():
            try:
                processed = await self.drain()
            except asyncio.CancelledError:
                raise
            except Exception:
                # Die Schleife darf nie sterben — ein unerwarteter Fehler würde
                # sonst jede weitere Extraktion stillschweigend verhindern.
                log.exception("worker.loop_error")
                processed = 0
            if processed == 0:
                await jobs_service.wait_for_work(self._settings.worker_idle_seconds)

    async def drain(self) -> int:
        """Alle fälligen Jobs abarbeiten; Anzahl zurückgeben."""
        file_store = FileStore(self._settings.media_dir)
        model = build_vision_model(self._settings)
        processed = 0

        while not self._stopping.is_set():
            async with get_sessionmaker()() as session:
                job = await jobs_service.claim_next(session)
                if job is None:
                    return processed

                outcome = await extraction_service.process_receipt(
                    session,
                    job.receipt_id,
                    settings=self._settings,
                    file_store=file_store,
                    model=model,
                )
                if outcome.error is not None and outcome.status.value == "failed":
                    retrying = await jobs_service.mark_failed(
                        session,
                        job,
                        outcome.error,
                        max_attempts=self._settings.worker_max_attempts,
                    )
                    log.warning(
                        "worker.job_failed",
                        extra={
                            "job_id": job.id,
                            "receipt_id": job.receipt_id,
                            "attempt": job.attempts,
                            "retrying": retrying,
                        },
                    )
                else:
                    await jobs_service.mark_done(session, job)
                processed += 1

        return processed


async def run_pending_jobs(settings: Settings) -> int:
    """Alle offenen Jobs einmal abarbeiten — für Tests und einen möglichen
    CLI-Aufruf, ohne die Dauerschleife zu starten."""
    return await Worker(settings).drain()
