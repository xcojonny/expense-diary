"""Health — bewusst ohne Auth, damit der Docker-Healthcheck ihn erreicht.

Der Endpoint verrät nichts Vertrauliches, sagt aber genau die Dinge, die man
bei „irgendwas läuft nicht" wissen will: ist ein Modell einsatzbereit, und
stauen sich Jobs?
"""

from __future__ import annotations

import sqlalchemy as sa
from fastapi import APIRouter

from app.api.deps import SessionDep, SettingsDep
from app.integrations.llm import build_vision_model
from app.models import Job, JobStatus
from app.schemas import HealthOut

router = APIRouter(tags=["health"])

VERSION = "2.0.0"


@router.get("/health", response_model=HealthOut)
async def health(session: SessionDep, settings: SettingsDep) -> HealthOut:
    queued = (
        await session.execute(
            sa.select(sa.func.count(Job.id)).where(
                Job.status.in_((JobStatus.QUEUED.value, JobStatus.RUNNING.value))
            )
        )
    ).scalar_one()

    model = build_vision_model(settings)
    return HealthOut(
        status="ok",
        version=VERSION,
        auth_mode=settings.auth_mode.value,
        llm_provider=settings.llm_provider.value,
        llm_ready=model.available,
        queued_jobs=queued,
    )
