# Haushaltsbuch (expense-diary)

Self-hosted, AI-assisted household expense diary. Upload photos/PDFs of German
supermarket receipts; a vision LLM extracts each line item (name, quantity,
price, category); and — the actual point of the app — an **analysis layer**
turns that into monthly reports and savings insights: what's expensive, what
you buy too often, and per-item price trends over time.

The receipt scan is a solved, deliberately-thin standard problem. The value
lives in the analysis endpoints.

## Status — build phases

The project is built in phases (see the task brief). This repo currently holds:

- [x] **Phase 1 — Foundation:** data model, migrations, seeds, docker-compose,
      backend skeleton (FastAPI + async SQLAlchemy + Alembic), frontend scaffold
      (Nuxt 3 SPA + Tailwind + PWA), CI.
- [x] **Phase 2 — Upload + async extraction pipeline (LLM adapter) + status
      polling:** upload endpoint (type/size-hardened), provider-agnostic vision
      adapter (openai/ollama/null), pure JSON parser + consistency check, ARQ
      worker (with a BackgroundTasks fallback), receipt/category endpoints, and
      a functional upload page that polls until extraction finishes.
- [x] **Phase 3 — Dashboard:** receipt list, and a detail view with editable
      line items (add/edit/delete, header edit, confirm-review, delete receipt).
      Edits re-map to the group's Item catalog exactly like extraction does.
- [x] **Phase 4 — Analysis layer** *(the heart)*: pure aggregation domain
      (monthly report, over-buying, expensive food + budget share, per-item
      price trend, previous-month comparison) with the math unit-tested; analytics
      endpoints; and a report page with month navigation, category/store bars,
      and a dependency-free SVG price-trend chart.
- [x] **Phase 5 — Category management + manual correction:** category CRUD
      (create/rename/reparent/delete) with duplicate-name and cycle guards and a
      management page; manual line-item correction was delivered in phase 3. **← done**

All five build phases are implemented.

Beyond the brief:

- [x] **Multi-tenancy + auth:** users, households with roles (admin/member) and
      email invitations, a per-request active-group seam. Login via **magic link**
      or **OIDC SSO (Authelia)** — no passwords; the app issues its own JWT access +
      rotating refresh session. See `docs/architecture.md` §6.
- [x] **Release workflow:** `.github/workflows/release.yml` builds & pushes the
      backend/frontend images to GHCR on green CI / version tags.

## Stack

- **Backend:** FastAPI, SQLAlchemy 2 (async), PostgreSQL 16, Alembic, ARQ + Redis
  worker (async extraction), `uv`-managed.
- **Frontend:** Nuxt 3 SPA (`ssr: false`), TypeScript strict, Pinia, Tailwind, PWA.
- **Auth:** magic-link + OIDC (Authelia); JWT access + httpOnly rotating refresh.
- **LLM:** provider-agnostic adapter (`backend/app/integrations/llm/`). Default is
  an OpenAI-Vision-compatible endpoint; swap to local Ollama by changing ENV only.
- **Deployment:** docker-compose (db, redis, backend, worker, frontend); images on GHCR.

## Architecture at a glance

```
backend/app/
├── core/           # config (all ENV), logging
├── db/             # engine, sessionmaker, Base + naming conventions
├── models/         # Receipt, LineItem, Category, Item
├── domain/         # ★ PURE, I/O-free logic — normalize.py (+ aggregation, phase 4)
├── services/       # use-cases: upload, extraction, analysis (phase 2+)
├── integrations/
│   ├── llm/        #   vision-LLM adapter (openai / ollama / null fallback)
│   └── storage/    #   local media storage
├── prompts/        # editable extraction prompt (receipt_extraction.de.txt)
├── workers/        # ARQ settings + tasks (phase 2)
└── api/v1/         # health (+ receipts, categories, analytics in later phases)
```

**One hard rule:** `domain/` imports nothing from `services/`, `integrations/`
or `api/`. It is pure, synchronous, I/O-free logic (normalization, aggregation)
and it is where the unit tests concentrate. See
[`docs/architecture.md`](docs/architecture.md) for the data model and decisions.

## Quick start (local development)

Prerequisites: [`uv`](https://docs.astral.sh/uv/), Node 22 + `pnpm` (via
corepack), and either Docker (for `make dev-up`) or a local PostgreSQL 16 + Redis.

```bash
make install          # uv sync + pnpm install; creates backend/.env
make dev-up           # Postgres + Redis via docker-compose.dev.yml (+ expense_test DB)
make dev-backend      # migrate + seed, then uvicorn --reload on :8010
make dev-frontend     # Nuxt dev server on :3010 (proxies /api, /media → :8010)
```

Dev ports are deliberately **non-standard** so they don't clash with a native
Postgres/Redis (55432 / 56379) or another local app (API :8010, frontend :3010).
Override via `BACKEND_PORT` / `FRONTEND_PORT` / `DEV_DB_PORT` / `DEV_REDIS_PORT`.

- API docs (dev only): http://localhost:8010/api/docs
- Health: http://localhost:8010/api/v1/healthz · readiness: `/api/v1/readyz`

`make check` runs exactly what CI runs (ruff + mypy + pytest, eslint + vue-tsc +
vitest). `make help` lists every target.

## Environment variables

Backend settings live in `backend/app/core/config.py`; template:
`backend/.env.example` (local dev) and `deploy/.env.example` (production).

| Variable | Default | Purpose |
|---|---|---|
| `APP_ENV` | `production` | `production` \| `development` \| `test` |
| `BASE_URL` | `http://localhost:3000` | Public frontend URL (dev `.env`: `:3010`) |
| `DATABASE_URL` | `…@localhost:5432/expense` (dev `.env`: `:55432`) | Async Postgres DSN |
| `REDIS_URL` | `redis://localhost:6379/0` (dev `.env`: `:56379`) | Redis (ARQ worker + rate limits) |
| `MEDIA_DIR` | `./.data/media` (dev) / `/data/media` (Docker) | Uploaded receipt files |
| `DEFAULT_LOCALE` | `de` | Default UI/mail language |
| `UPLOAD_MAX_BYTES` | `15728640` | Max receipt file size (15 MiB) |
| `LLM_PROVIDER` | `none` | `none` \| `openai` \| `ollama` — `none` = rule-based fallback |
| `LLM_API_KEY` | – | API key for the vision LLM |
| `LLM_BASE_URL` | `https://api.openai.com/v1` | OpenAI-compatible or Ollama endpoint |
| `LLM_MODEL` | `gpt-4o-mini` | Vision model name |
| `LLM_TIMEOUT_SECONDS` | `90` | Per-request LLM timeout |
| `SECRET_KEY` | `change-me` | JWT signing — set a strong value in prod |
| `INITIAL_ADMIN_EMAIL` | – | Bootstrapped active admin + default-group owner |
| `COOKIE_SECURE` | `true` | `false` for plain-HTTP local dev (else no refresh cookie) |
| `SMTP_HOST` | – | Empty ⇒ magic-link/invite links are logged, not sent |
| `SMTP_PORT` / `SMTP_USER` / `SMTP_PASSWORD` / `SMTP_STARTTLS` | – | SMTP delivery |
| `MAIL_FROM` / `MAIL_FROM_NAME` | `haushaltsbuch@example.org` / `Haushaltsbuch` | Sender |
| `OIDC_ISSUER` | – | Empty ⇒ SSO disabled; else the OIDC provider (Authelia) |
| `OIDC_CLIENT_ID` / `OIDC_CLIENT_SECRET` | – | Confidential OIDC client credentials |
| `OIDC_PROVIDER_NAME` | `Authelia` | Login-button label |

`LLM_PROVIDER=none` keeps the app fully runnable without any LLM configured:
extraction falls back to a no-op and receipts land in `needs_review` for manual
entry, so nothing hard-depends on an external model.

## Auth & SSO

No passwords — log in via a **magic link** (emailed; with no `SMTP_HOST` the link
is written to the backend log for local dev) or **OIDC SSO** against Authelia (or
any OIDC provider). The app issues its own session (short-lived JWT access token +
rotating httpOnly refresh cookie). The first login uses `INITIAL_ADMIN_EMAIL`
(request a magic link for it). Register the OIDC client in Authelia with redirect
URI `{API_BASE_URL}/api/v1/auth/oidc/callback` — see `docs/architecture.md` §6.2.
Households are multi-tenant: users can belong to several, switch the active one in
the header, and admins invite members by email.

## Deployment

`deploy/docker-compose.yml` runs the full stack (db, redis, one-shot migrate,
backend, worker, frontend). Configure via `deploy/.env` (template:
`deploy/.env.example`) and front it with a reverse proxy that terminates TLS and
routes `/api` + `/media` to the backend and everything else to the frontend.

## License

See [`LICENSE`](LICENSE).
