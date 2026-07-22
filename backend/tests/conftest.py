import os
from pathlib import Path

# Environment MUST be set before any app import (settings are cached via lru_cache).
os.environ.setdefault(
    "DATABASE_URL", "postgresql+asyncpg://expense:expense@localhost:5432/expense_test"
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("BASE_URL", "http://testserver")
os.environ.setdefault("MEDIA_DIR", "/tmp/expense-test-media")

BACKEND_DIR = Path(__file__).resolve().parent.parent
