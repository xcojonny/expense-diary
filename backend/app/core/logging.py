import logging

import structlog

from app.core.config import get_settings


def configure_logging() -> None:
    """Structured logging: human-readable console in dev, JSON in production."""
    settings = get_settings()
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer() if settings.is_dev else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
