# Ein Image für die ganze App (ADR-006): Stage 1 baut die SPA, Stage 2 liefert
# API und SPA aus einem Prozess aus. Kein nginx, kein migrate-Container, kein
# Worker-Container.

# --- Stage 1: SPA bauen -------------------------------------------------------
FROM node:22-alpine AS web

RUN corepack enable
WORKDIR /src/frontend

# Erst die Manifeste, damit der Abhängigkeits-Layer gecacht bleibt.
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile

COPY frontend/ ./
# `build:only` überspringt vue-tsc — der Typecheck läuft in der CI, nicht im
# Image-Build. Ausgabeziel ist laut vite.config ../backend/app/static.
RUN pnpm run build:only


# --- Stage 2: Laufzeit --------------------------------------------------------
FROM python:3.12-slim AS runtime

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/app/.venv/bin:$PATH" \
    APP_ENV=production \
    DATA_DIR=/data \
    LOG_FORMAT=json

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /usr/local/bin/uv

WORKDIR /app

# Abhängigkeiten aus dem Lockfile, ohne das Projekt selbst zu installieren —
# der Code kommt als Quelle darunter und wird direkt ausgeführt.
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY backend/alembic.ini ./
COPY backend/alembic/ ./alembic/
COPY backend/app/ ./app/
COPY --from=web /src/backend/app/static/ ./app/static/

# Nicht als root laufen. /data ist das Volume (SQLite-Datei + Belege).
RUN groupadd --gid 10001 app \
    && useradd --uid 10001 --gid app --home /app --shell /usr/sbin/nologin app \
    && mkdir -p /data \
    && chown -R app:app /app /data
USER app

VOLUME ["/data"]
EXPOSE 8000

# Der Healthcheck braucht keine Auth (siehe api/routes/health.py).
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request as u; u.urlopen('http://127.0.0.1:8000/api/health', timeout=4)"

# Ein Worker: SQLite hat einen Schreiber, und der Extraktions-Worker läuft im
# selben Prozess (ADR-002). Mehr Worker würden mehrfach extrahieren.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
