# Die wichtigen Kommandos. `make check` läuft ohne jeden externen Dienst —
# kein Postgres, kein Redis, kein Docker (ADR-010).
#
# Voraussetzungen: uv (Backend), Node 22 + pnpm via corepack (Frontend).

.DEFAULT_GOAL := help

BACKEND  := cd backend &&
FRONTEND := cd frontend &&

.PHONY: help
help: ## Diese Übersicht
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

# -- Einrichten ----------------------------------------------------------------

.PHONY: install
install: ## Abhängigkeiten installieren (uv sync + pnpm install)
	$(BACKEND) uv sync
	$(FRONTEND) pnpm install
	@[ -f .env ] || (cp .env.example .env && \
		echo "→ .env aus .env.example erstellt — AUTH_PASSWORD und SECRET_KEY setzen")

# -- Entwicklung ---------------------------------------------------------------
# Zwei Terminals: `make dev` für die API, `make dev-web` für die SPA mit
# Hot-Reload. Der Vite-Dev-Server proxyt /api auf :8000.

.PHONY: dev
dev: ## API mit Auto-Reload auf :8000 (migriert und seedet beim Start)
	$(BACKEND) DATA_DIR=../data AUTH_PASSWORD=$${AUTH_PASSWORD:-dev} \
		uv run uvicorn app.main:app --reload --port 8000

.PHONY: dev-web
dev-web: ## Vite-Dev-Server auf :5173 (proxyt /api auf :8000)
	$(FRONTEND) pnpm dev

# -- Qualität ------------------------------------------------------------------

.PHONY: lint
lint: ## ruff + eslint
	$(BACKEND) uv run ruff check .
	$(FRONTEND) pnpm lint

.PHONY: format
format: ## Automatisch behebbare Lint-Funde beheben
	$(BACKEND) uv run ruff check . --fix
	$(FRONTEND) pnpm lint:fix

.PHONY: typecheck
typecheck: ## mypy (strict) + vue-tsc
	$(BACKEND) uv run mypy app
	$(FRONTEND) pnpm typecheck

.PHONY: test
test: ## pytest + vitest — ohne externe Dienste
	$(BACKEND) uv run pytest
	$(FRONTEND) pnpm test

.PHONY: check
check: lint typecheck test ## Alles, was die CI prüft

# -- Datenbank -----------------------------------------------------------------
# Im Normalbetrieb nicht nötig: die App migriert beim Start.

.PHONY: migrate
migrate: ## Migrationen anwenden
	$(BACKEND) DATA_DIR=../data uv run alembic upgrade head

.PHONY: migration
migration: ## Migration erzeugen: make migration m="beschreibung"
	@[ -n "$(m)" ] || { echo '→ make migration m="beschreibung"'; exit 1; }
	$(BACKEND) DATA_DIR=../data uv run alembic revision --autogenerate -m "$(m)"

# -- Container -----------------------------------------------------------------

.PHONY: build
build: ## SPA bauen und ins Backend legen (backend/app/static)
	$(FRONTEND) pnpm build

.PHONY: image
image: ## Docker-Image bauen
	docker compose build

.PHONY: up
up: ## Container starten (baut bei Bedarf)
	@[ -f .env ] || (cp .env.example .env && echo "→ .env erstellt — bitte anpassen")
	docker compose up -d --build
	@echo "→ http://localhost:$${HOST_PORT:-8000}"

.PHONY: down
down: ## Container stoppen
	docker compose down

.PHONY: logs
logs: ## Logs verfolgen
	docker compose logs -f app

.PHONY: clean
clean: ## Build-Artefakte und Caches entfernen (Daten bleiben)
	rm -rf backend/app/static backend/.pytest_cache backend/.mypy_cache backend/.ruff_cache
	rm -rf frontend/dist frontend/dev-dist
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
