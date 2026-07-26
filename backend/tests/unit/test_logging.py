"""Unit tests for the admin log ring: it must degrade to the local in-memory
ring (never raise) when the Redis-backed shared ring is unavailable."""

import time

import pytest

import app.core.logging as logmod


def test_get_recent_logs_falls_back_to_local_ring(monkeypatch: pytest.MonkeyPatch) -> None:
    # Simulate "Redis unavailable": no cached client + an active cooldown window.
    monkeypatch.setattr(logmod, "_redis_client", None)
    monkeypatch.setattr(logmod, "_redis_retry_at", time.monotonic() + 3600)

    assert logmod._redis_sink() is None
    assert logmod._read_from_redis() is None

    logmod._LOG_RING.clear()
    event = {"event": "local-only", "level": "warning", "timestamp": "2026-07-26T00:00:00Z"}
    # Must not raise even though the Redis sink is down.
    logmod._capture_to_ring(None, "warning", event)

    logs = logmod.get_recent_logs(limit=50)
    assert any(e["event"] == "local-only" for e in logs)


def test_min_level_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(logmod, "_redis_client", None)
    monkeypatch.setattr(logmod, "_redis_retry_at", time.monotonic() + 3600)

    logmod._LOG_RING.clear()
    logmod._capture_to_ring(None, "info", {"event": "an-info", "level": "info", "timestamp": "t"})
    logmod._capture_to_ring(None, "error", {"event": "an-error", "level": "error", "timestamp": "t"})

    events = {e["event"] for e in logmod.get_recent_logs(min_level="warning")}
    assert "an-error" in events
    assert "an-info" not in events
