import collections
import json
import logging
import time
from typing import Any

import redis
import structlog

from app.core.config import get_settings

# In-memory ring of the most recent log events, so an instance admin can read
# them in the UI without shelling into the container. Per process and in-memory
# only: it holds *this* process's logs since the last restart. It is the
# fallback for the Redis-backed shared ring below (used when Redis is down —
# in which case extraction runs in-process anyway, so the API ring already holds
# those events). Kept small and bounded — never a durable log store.
_LOG_RING_MAXLEN = 1000
_LOG_RING: collections.deque[dict[str, Any]] = collections.deque(maxlen=_LOG_RING_MAXLEN)

# Redis-backed shared ring so the admin log view sees events from *every* backend
# process — critically the ARQ worker, where the whole receipt-extraction +
# vision-LLM pipeline runs. Without this the admin only ever sees the API
# process's own logs (essentially just "startup complete"), which is exactly why
# the log view looks empty. Best-effort: any Redis hiccup falls back to the local
# in-memory ring and backs off, so logging never blocks or fails on Redis.
_REDIS_LOG_KEY = "expense:logs:ring"
_REDIS_SINK_TIMEOUT = 0.5  # seconds — keep the log path from stalling on Redis
_REDIS_SINK_COOLDOWN = 30.0  # back off this long after a Redis error

_redis_client: Any = None
_redis_retry_at = 0.0

_LEVEL_ORDER = {
    "debug": 10,
    "info": 20,
    "warning": 30,
    "warn": 30,
    "error": 40,
    "critical": 50,
}
_RESERVED = {"event", "level", "timestamp", "logger", "logger_name"}


def _redis_sink() -> Any:
    """Lazily create a short-timeout *sync* Redis client for the log sink, or
    return None while we're in a post-error cooldown. Best-effort only."""
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    if time.monotonic() < _redis_retry_at:
        return None
    try:
        _redis_client = redis.Redis.from_url(
            get_settings().redis_url,
            socket_connect_timeout=_REDIS_SINK_TIMEOUT,
            socket_timeout=_REDIS_SINK_TIMEOUT,
        )
    except Exception:  # pragma: no cover — bad URL etc.; sink is best-effort
        _drop_redis_sink()
        return None
    return _redis_client


def _drop_redis_sink() -> None:
    """Disable the Redis sink for a cooldown window after an error, so a dead or
    slow Redis doesn't stall every subsequent log call."""
    global _redis_client, _redis_retry_at
    _redis_client = None
    _redis_retry_at = time.monotonic() + _REDIS_SINK_COOLDOWN


def _push_to_redis(entry: dict[str, Any]) -> None:
    client = _redis_sink()
    if client is None:
        return
    try:
        pipe = client.pipeline(transaction=False)
        pipe.lpush(_REDIS_LOG_KEY, json.dumps(entry, default=str))
        pipe.ltrim(_REDIS_LOG_KEY, 0, _LOG_RING_MAXLEN - 1)
        pipe.execute()
    except Exception:  # pragma: no cover — sink is best-effort
        _drop_redis_sink()


def _read_from_redis() -> list[dict[str, Any]] | None:
    """Recent events from the shared ring, oldest→newest, or None if Redis is
    unavailable (caller then falls back to the local in-memory ring)."""
    client = _redis_sink()
    if client is None:
        return None
    try:
        raw = client.lrange(_REDIS_LOG_KEY, 0, _LOG_RING_MAXLEN - 1)
    except Exception:  # pragma: no cover — sink is best-effort
        _drop_redis_sink()
        return None
    entries: list[dict[str, Any]] = []
    for item in reversed(raw):  # stored newest-first (LPUSH) → oldest-first
        try:
            entries.append(json.loads(item))
        except (ValueError, TypeError):  # pragma: no cover — skip a corrupt line
            continue
    return entries


def _capture_to_ring(
    _logger: Any, method_name: str, event_dict: structlog.types.EventDict
) -> structlog.types.EventDict:
    """structlog processor: snapshot each event into the local + shared rings,
    then pass it through unchanged. Runs after level/timestamp are added, before
    rendering. Never raises — logging must not fail because capture failed."""
    try:
        context = {
            key: str(value) for key, value in event_dict.items() if key not in _RESERVED
        }
        entry = {
            "timestamp": event_dict.get("timestamp"),
            "level": str(event_dict.get("level") or method_name),
            "event": str(event_dict.get("event", "")),
            "logger": event_dict.get("logger") or event_dict.get("logger_name"),
            "context": context,
        }
        _LOG_RING.append(entry)
        _push_to_redis(entry)
    except Exception:  # pragma: no cover — capture is best-effort
        pass
    return event_dict


def get_recent_logs(limit: int = 200, min_level: str | None = None) -> list[dict[str, Any]]:
    """Recent log events, oldest→newest, optionally filtered to a minimum level
    (e.g. ``warning``). Returns at most ``limit`` entries (the newest ones).

    Reads the Redis-backed shared ring so events from all processes (API +
    worker) are visible; falls back to this process's in-memory ring if Redis is
    unreachable."""
    entries = _read_from_redis()
    if not entries:
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
