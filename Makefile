# expense-diary — the important commands.
# Prerequisites: uv (backend), Node 22 + pnpm via corepack (frontend),
# PostgreSQL 16 + Redis. Bring your own, OR:
#   make dev-up    # Postgres + Redis via docker-compose.dev.yml

.DEFAULT_GOAL := help

BACKEND  := cd backend &&
FRONTEND := cd frontend &&

# Dev ports are deliberately NON-standard so they don't clash with other local
# services. Override if needed:
#   make dev-backend dev-frontend BACKEND_PORT=8000
BACKEND_PORT  ?= 8010   # API (uvicorn); standard 8000 avoided
FRONTEND_PORT ?= 3010   # Nuxt dev server; standard 3000 avoided
export BACKEND_PORT FRONTEND_PORT

# Host ports of the dev infra (docker-compose.dev.yml) — non-standard to avoid
# a native Postgres/Redis on 5432/6379. Adjust backend/.env DATABASE_URL/REDIS_URL
# to match if you change these.
DEV_DB_PORT    ?= 55432
DEV_REDIS_PORT ?= 56379
export DEV_DB_PORT DEV_REDIS_PORT

# -- Meta ----------------------------------------------------------------------

.PHONY: help
help: ## This overview
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Install dependencies (uv sync + pnpm install) + create backend/.env
	$(BACKEND) uv sync
	$(FRONTEND) pnpm install
	@[ -f backend/.env ] || (cp backend/.env.example backend/.env && \
		echo "→ backend/.env created from .env.example (local defaults, not for prod)")

# -- Development ---------------------------------------------------------------

.PHONY: dev-up
dev-up: ## Start Postgres + Redis for local development (docker-compose.dev.yml)
	docker compose -f docker-compose.dev.yml up -d
	@until docker compose -f docker-compose.dev.yml exec -T db pg_isready -U expense >/dev/null 2>&1; do sleep 1; done
	@# expense_test (for pytest) is not created by POSTGRES_DB — add it once.
	@docker compose -f docker-compose.dev.yml exec -T db psql -U expense -d expense -tc \
		"SELECT 1 FROM pg_database WHERE datname = 'expense_test'" | grep -q 1 || \
		docker compose -f docker-compose.dev.yml exec -T db createdb -U expense expense_test
	@echo "→ Postgres :$(DEV_DB_PORT), Redis :$(DEV_REDIS_PORT)"

.PHONY: dev-down
dev-down: ## Stop the dev infrastructure
	docker compose -f docker-compose.dev.yml down

.PHONY: dev-backend
dev-backend: migrate seed ## Migrate + seed + API with auto-reload on :$(BACKEND_PORT)
	$(BACKEND) uv run uvicorn app.main:app --reload --port $(BACKEND_PORT)

.PHONY: dev-frontend
dev-frontend: ## Nuxt dev server on :$(FRONTEND_PORT) (proxies /api, /media → BACKEND_PORT)
	$(FRONTEND) pnpm dev

# -- Database ------------------------------------------------------------------

.PHONY: migrate
migrate: ## Apply Alembic migrations
	$(BACKEND) uv run alembic upgrade head

.PHONY: migration
migration: ## Autogenerate a migration: make migration m="description"
	$(BACKEND) uv run alembic revision --autogenerate -m "$(m)"

.PHONY: seed
seed: ## Seed master data (idempotent)
	$(BACKEND) uv run python -m app.seed

# -- Quality -------------------------------------------------------------------

.PHONY: lint
lint: ## ruff + eslint
	$(BACKEND) uv run ruff check .
	$(FRONTEND) pnpm lint

.PHONY: typecheck
typecheck: ## mypy (strict) + vue-tsc
	$(BACKEND) uv run mypy app
	$(FRONTEND) pnpm typecheck

.PHONY: test
test: ## pytest (needs Postgres) + vitest
	$(BACKEND) uv run pytest
	$(FRONTEND) pnpm test

.PHONY: check
check: lint typecheck test ## Everything CI runs

# -- Build ---------------------------------------------------------------------

.PHONY: build
build: ## Build both Docker images locally
	docker build -t expense-diary-backend ./backend
	docker build -t expense-diary-frontend ./frontend
