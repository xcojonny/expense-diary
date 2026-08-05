from __future__ import annotations

from datetime import datetime
from enum import StrEnum

import sqlalchemy as sa
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin


class JobStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class Job(Base, TimestampMixin):
    """Ein Extraktionsauftrag — die Queue ist eine Tabelle (ADR-002).

    Zwei Dinge, die die Redis/ARQ-Variante nicht hatte, fallen dabei ab:
    Aufträge überleben einen Neustart, und man kann sie mit `SELECT` ansehen.
    `run_after` trägt das Backoff eines fehlgeschlagenen Versuchs.
    """

    __tablename__ = "jobs"
    __table_args__ = (
        sa.CheckConstraint(
            "status IN ('queued','running','done','failed')", name="ck_jobs_status"
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(
        sa.ForeignKey("receipts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        sa.String(12), default=JobStatus.QUEUED.value, nullable=False, index=True
    )
    attempts: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    run_after: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True, index=True)
    error: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
