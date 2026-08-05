"""Job-Queue als Tabelle (ADR-002).

Die einzige Schnittstelle zur Queue. Wer echte Queue-Semantik braucht, ersetzt
diese Datei und lässt den Rest der App unberührt.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, cast

import sqlalchemy as sa
from sqlalchemy import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.base import utcnow
from app.models import Job, JobStatus

log = get_logger(__name__)

# Der Worker wartet auf dieses Event, statt in einer Schleife zu pollen — ein
# Upload wird dadurch sofort verarbeitet und nicht erst beim nächsten Tick.
_wakeup = asyncio.Event()


def wake_worker() -> None:
    _wakeup.set()


async def wait_for_work(timeout: float) -> None:  # noqa: ASYNC109
    """Auf einen neuen Job warten (oder nach `timeout` von selbst aufwachen —
    das fängt Jobs auf, deren Backoff abgelaufen ist)."""
    try:
        await asyncio.wait_for(_wakeup.wait(), timeout=timeout)
    except TimeoutError:
        pass
    finally:
        _wakeup.clear()


async def enqueue(session: AsyncSession, receipt_id: int) -> Job:
    job = Job(receipt_id=receipt_id, status=JobStatus.QUEUED.value)
    session.add(job)
    await session.flush()
    return job


async def claim_next(session: AsyncSession) -> Job | None:
    """Den nächsten fälligen Job auf `running` setzen und zurückgeben.

    Das `WHERE status='queued'` im UPDATE ist die Absicherung: selbst wenn
    irgendwann zwei Worker laufen, bekommt nur einer den Job.
    """
    now = utcnow()
    job_id = (
        await session.execute(
            sa.select(Job.id)
            .where(
                Job.status == JobStatus.QUEUED.value,
                sa.or_(Job.run_after.is_(None), Job.run_after <= now),
            )
            .order_by(Job.id)
            .limit(1)
        )
    ).scalar_one_or_none()
    if job_id is None:
        return None

    result = cast(
        "CursorResult[Any]",
        await session.execute(
            sa.update(Job)
            .where(Job.id == job_id, Job.status == JobStatus.QUEUED.value)
            .values(status=JobStatus.RUNNING.value, started_at=now, attempts=Job.attempts + 1)
        ),
    )
    await session.commit()
    if result.rowcount != 1:  # ein anderer war schneller
        return None
    return await session.get(Job, job_id)


async def mark_done(session: AsyncSession, job: Job) -> None:
    job.status = JobStatus.DONE.value
    job.finished_at = utcnow()
    job.error = None
    await session.commit()


async def mark_failed(session: AsyncSession, job: Job, error: str, *, max_attempts: int) -> bool:
    """Fehlversuch verbuchen. `True`, wenn erneut versucht wird.

    Backoff wächst linear (30 s, 60 s, …) — bei einem Haushalt reicht das, und
    es hält einen zickigen Provider aus, ohne ihn zu hämmern.
    """
    job.error = error[:2000]
    retry = job.attempts < max_attempts
    if retry:
        job.status = JobStatus.QUEUED.value
        job.run_after = utcnow() + timedelta(seconds=30 * job.attempts)
    else:
        job.status = JobStatus.FAILED.value
        job.finished_at = utcnow()
    await session.commit()
    return retry


async def requeue_stale(session: AsyncSession) -> int:
    """Beim Start hängende `running`-Jobs zurück in die Queue.

    Crash-Recovery, die es mit der Redis-Variante nicht gab: wer mitten in der
    Extraktion neu startet, verliert den Auftrag nicht.
    """
    result = cast(
        "CursorResult[Any]",
        await session.execute(
            sa.update(Job)
            .where(Job.status == JobStatus.RUNNING.value)
            .values(status=JobStatus.QUEUED.value, started_at=None)
        ),
    )
    await session.commit()
    count = result.rowcount or 0
    if count:
        log.info("jobs.requeued_stale", extra={"count": count})
    return count
