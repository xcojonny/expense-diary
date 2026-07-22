# CLAUDE.md

Guidance for AI agents (and humans) working in this repository.

## What this is

**expense-diary** ("Haushaltsbuch") is a self-hosted, AI-assisted household
expense diary for a private homelab. The loop: **upload a receipt photo/PDF → a
vision LLM extracts each line item → an analysis layer reports spending and
savings potential** (expensive items, over-buying, per-item price trends).

The value is the **analysis layer**, not the scan — keep the scan thin. Built in
five phases; phase 1 (foundation) is done. See `README.md` for phase status.

Monorepo:

- `backend/` — FastAPI + SQLAlchemy 2 (async) + Alembic, PostgreSQL 16, ARQ + Redis worker.
- `frontend/` — Nuxt 3 SPA (`ssr: false`), TypeScript strict, Tailwind, PWA, pnpm.
- `docs/` — source-of-truth docs (read before large changes).
- `deploy/` — docker-compose production stack.

## Read these first

| File | Why |
|---|---|
| `docs/anforderungen.md` | Requirements — the source of truth for *what* to build. |
| `docs/architecture.md` | Data model (ERD), status flow, normalization, pipeline, decisions. |

If you change the data model, background jobs, or an architectural decision,
update `docs/architecture.md` in the same change. Scope changes go in
`docs/anforderungen.md`.

## Language & style conventions

- **Code, comments, commit messages, identifiers, this file: English.**
- **User-facing strings: German** (`de` default; `en` prepared for later).
  Backend user-facing strings (HTTP error details) are German too.
- Match the surrounding code's idiom and comment density. Comments explain *why*.
- Commit style: Conventional Commits with a German subject, e.g.
  `feat(analyse): Monatsbericht-Endpoint`. Keep the scope in parens.

## Commands (use the Makefile)

`make help` lists everything. The important ones:

```bash
make install      # uv sync + pnpm install; creates backend/.env
make dev-up       # Postgres + Redis via docker-compose.dev.yml (+ expense_test DB)
make dev-backend  # migrate + seed, then uvicorn --reload on :8000
make dev-frontend # Nuxt dev server on :3000 (proxies /api, /media → backend)
make dev-down     # stop the dev infra

make migrate                    # alembic upgrade head
make migration m="beschreibung" # autogenerate a revision
make seed                       # idempotent master data (categories)

make lint · make typecheck · make test
make check   # lint + typecheck + test — exactly what CI runs
make build   # build both Docker images
```

Backend tooling runs through `uv` (from `backend/`); frontend through `pnpm`
(from `frontend/`, via corepack). Don't use `npm` or `pip` directly.

## Backend layout & the one hard rule

```
backend/app/
├── main.py         # app factory, lifespan, router mount, /media, health
├── core/           # config (all ENV), logging
├── db/             # engine, sessionmaker, Base + naming conventions
├── models/         # group, receipt, line_item, category, item
├── schemas/        # Pydantic v2 DTOs (receipt, category)
├── domain/         # ★ PURE, I/O-free logic — normalize, extraction, upload, aggregation
├── services/       # use-cases: upload, extraction, group, items, receipt_edit, analytics, category
├── integrations/
│   ├── llm/        #   vision-LLM adapter: base protocol + openai_compatible / null
│   └── storage/    #   local media storage + pdf first-image
├── prompts/        # editable extraction prompt(s) + loader
├── workers/        # ARQ settings + tasks (extract_receipt_task)
└── api/v1/         # health, receipts, categories, analytics; deps.py = tenancy seam
```

**The one architectural rule that must not be broken:** `domain/` imports
nothing from `api/`, `services/`, or `integrations/`. It is pure, synchronous,
I/O-free logic — normalization, aggregation math — and it is where the unit
tests concentrate. Anything touching the DB, network, or Redis goes in
`services/` or `integrations/`, never in `domain/`.

`integrations/llm` hides the model behind an interface so `LLM_PROVIDER`
(`openai` / `ollama` / `none`) switches providers with no service changes; every
LLM path must degrade gracefully to the rule-based/no-op fallback.

## Frontend layout

```
frontend/app/
├── pages/          # file-routed: index (Dashboard), upload, bericht, kategorien
├── components/      # (phase 3)
├── composables/     # useApi, useReceiptPolling (2s status polling)
├── stores/          # Pinia
└── types/           # models.ts (track the backend OpenAPI schema)
```

Frontend types track the backend OpenAPI schema (`pnpm generate:api` →
`types/api.d.ts`). When a backend response shape changes, update the TS type.

## Testing

- `backend/tests/unit/` — `domain/` logic (normalize, extraction parsing,
  aggregation math). Fast, no I/O. **Prefer adding coverage here** for domain logic;
  the analysis aggregations are the critical logic and are unit-tested here.
- `backend/tests/integration/` — API against a **real** Postgres (`expense_test`).
  DB is migrated + seeded once per session; `app_client` yields an httpx client
  over the ASGI app; receipts/items are cleared between tests (categories stay).
- `frontend/tests/` — vitest.
- `make check` is the gate CI enforces.

## Gotchas

- **Async SQLAlchemy `MissingGreenlet`.** Lazy-loading a relationship outside an
  awaited context throws. Eager-load what you serialize.
- **Server-side defaults apply at flush, not construction.** A column filled by
  `server_default` is `None` on the in-memory object until flush — set it in the
  constructor if you read it before commit.
- **CITEXT needs the extension.** The initial migration runs
  `CREATE EXTENSION IF NOT EXISTS citext`; keep it when regenerating migrations.
- **LLM is optional.** `LLM_PROVIDER=none` (default) → extraction falls back to a
  no-op and receipts land in `needs_review`; the app runs with no model configured.
- **Polling, not WebSocket.** Receipt status is polled (~2 s) by design — the
  backend stays stateless. Don't add a WebSocket without revisiting that.
- **Tenancy via one seam.** `Receipt`/`Item` are group-owned (`group_id`). Real
  multi-group auth isn't built yet, so a default group is bootstrapped and
  `api/deps.get_current_group_id` resolves it. Depend on that dependency for the
  active group in every new endpoint — never hard-code a group — so auth drops
  in later without touching endpoints. `Item` is unique per `(group_id, normalized_name)`.
- **Extraction runs off the request path.** Prefer the ARQ worker; the upload
  endpoint falls back to FastAPI BackgroundTasks when Redis is down. All output
  interpretation lives in the pure `domain/extraction.py` (parse + consistency),
  so test it there — not through the service.
- **`backend/.env.example` targets non-Docker local dev** — `MEDIA_DIR` is
  relative (`./.data/media`); the Docker image uses `/data/media`.

## Branch & PR workflow

- Develop on the session branch (`claude/…`); push with `git push -u origin <branch>`.
  Never commit directly to `main`.
- Run `make check` before pushing. If tests fail, say so plainly.
