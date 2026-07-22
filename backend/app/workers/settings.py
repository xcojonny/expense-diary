from collections.abc import Callable
from typing import ClassVar

from arq.connections import RedisSettings

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.tasks import extract_receipt_task


async def startup(ctx: object) -> None:
    configure_logging()


class WorkerSettings:
    """ARQ worker entrypoint: `arq app.workers.settings.WorkerSettings`.
    Runs the async receipt-extraction pipeline off the request path."""

    functions: ClassVar[list[Callable[..., object]]] = [extract_receipt_task]
    on_startup = startup
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
