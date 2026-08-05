"""Logging auf stdout — bewusst ohne Log-Ring und ohne Redis.

Der Altstand spiegelte jedes Ereignis in einen Redis-Ring, damit eine
Admin-Ansicht die Worker-Logs sehen konnte. Da Worker und API jetzt derselbe
Prozess sind (ADR-002), reicht stdout: `docker logs` ist das Werkzeug. Der
Fehlertext einer Extraktion wird zusätzlich am Bon gespeichert, weil man ihn
dort sucht.
"""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

_RESERVED = frozenset(
    {
        "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
        "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
        "created", "msecs", "relativeCreated", "thread", "threadName",
        "processName", "process", "taskName", "message", "asctime",
        # uvicorn hängt an jede Zeile eine ANSI-Variante seiner Meldung — im
        # eigenen Format ist das nur Rauschen.
        "color_message",
    }
)


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {k: v for k, v in record.__dict__.items() if k not in _RESERVED}


class TextFormatter(logging.Formatter):
    """`12:03:44 INFO  extraction.done receipt_id=7 items=23`"""

    def format(self, record: logging.LogRecord) -> str:
        base = f"{self.formatTime(record, '%H:%M:%S')} {record.levelname:<5} {record.getMessage()}"
        extras = " ".join(f"{k}={v}" for k, v in _extras(record).items())
        line = f"{base} {extras}".rstrip()
        if record.exc_info:
            line = f"{line}\n{self.formatException(record.exc_info)}"
        return line


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S"),
            "level": record.levelname,
            "event": record.getMessage(),
            "logger": record.name,
            **_extras(record),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: str = "INFO", fmt: str = "text") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())

    # uvicorn bringt eigene Handler mit — sonst steht jede Zeile doppelt da.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        logger = logging.getLogger(name)
        logger.handlers.clear()
        logger.propagate = True
    # Der Access-Log ist bei einem Haushalt Rauschen.
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    # Alembic protokolliert beim Start jedes geladene Plugin. Was zählt — ob eine
    # Migration lief — loggt die App selbst (`db.migrated`).
    logging.getLogger("alembic").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
