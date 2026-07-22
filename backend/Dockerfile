# --- Build stage: resolve dependencies with uv ------------------------------
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=0
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-dev
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# --- Runtime stage: slim, non-root -------------------------------------------
FROM python:3.12-slim-bookworm
RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /data/media && chown appuser /data/media
WORKDIR /app
COPY --from=builder --chown=appuser:appuser /app /app
# Git-SHA of the built image, injected by CI. Surfaced under /api/v1/version.
ARG GIT_SHA=""
ENV GIT_SHA=$GIT_SHA
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 MEDIA_DIR=/data/media
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/healthz', timeout=3)"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
