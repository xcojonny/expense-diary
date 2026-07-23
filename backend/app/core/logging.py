import collections
import logging
from typing import Any

import structlog

from app.core.config import get_settings

# In-memory ring of the most recent log events, so an instance admin can read
# them in the UI without shelling into the container. Per process and in-memory
# only: it holds the API/backend process's logs since the last restart (the ARQ
# worker is a separate process; its failures are also surfaced on the receipt's
# ``error`` field). Kept small and bounded — never a durable log store.
_LOG_RING_MAXLEN = 1000
_LOG_RING: collections.deque[dict[str, Any]] = collections.deque(maxlen=_LOG_RING_MAXLEN)

_LEVEL_ORDER = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "warn": 30,
    "error": 40,
    "critical": 50,
}
_RESERVED = {"event", "level", "timestamp", "logger", "logger_name"}


def _capture_to_ring(
    _logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """structlog processor: snapshot each event into the ring, then pass it
    through unchanged. Runs after level/timestamp are added, before rendering.
    Never raises — logging must not fail because capture failed."""
    try:
        context = {
            key: str(value) for key, value in event_dict.items() if key not in _RESERVED
        }
        _LOG_RING.append(
            {
                "timestamp": event_dict.get("timestamp"),
                "level": str(event_dict.get("level") or method_name),
                "event": str(event_dict.get("event", "")),
                "logger": event_dict.get("logger") or event_dict.get("logger_name"),
                "context": context,
            }
        )
    except Exception:  # pragma: no cover — capture is best-effort
        pass
    return event_dict


def get_recent_logs(limit: int = 200, min_level: str | None = None) -> list[dict[str, Any]]:
    """Recent log events, oldest→newest, optionally filtered to a minimum level
    (e.g. ``warning``). Returns at most ``limit`` entries (the newest ones)."""
    entries = list(_LOG_RING)
    if min_level:
        threshold = _LEVEL_ORDER.get(min_level.lower(), 0)
        entries = [e for e in entries if _LEVEL_ORDER.get(str(e["level"]).lower(), 0) >= threshold]
    return entries[-limit:]


def configure_logging() -> None:
    """Structured logging: human-readable console in dev, JSON in production.
    A ring-buffer sink keeps the most recent events for the admin log view."""
    settings = get_settings()
    renderer: structlog.types.Processor = (
        structlog.dev.ConsoleRenderer() if settings.is_dev else structlog.processors.JSONRenderer()
    )
    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _capture_to_ring,  # snapshot before rendering to a string
            renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)  # type: ignore[no-any-return]
