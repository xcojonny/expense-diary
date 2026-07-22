# Deployment

One production compose file at the repo root (`docker-compose.yml`) — the app
**and** the pull-deploy webhook. On the server it's just:

```bash
git pull && docker compose pull && docker compose up -d
```

Services: `db`, `redis`, one-shot `migrate`, `backend`, `worker`, `frontend`,
`docker-socket-proxy`, `deploy-webhook`. Config comes entirely from `.env`
(template: `.env.example`). `IMAGE_TAG` selects the running GHCR image tag — the
webhook flips it to `sha-<commit>`. (`docker-compose.dev.yml` is separate, for
local dev infra only.)

**Try it locally first:** `make prod-up` runs this same stack on your machine
with images built from source and ports published on `:8000` / `:8080` (no GHCR,
no Traefik, webhook off) — via the `docker-compose.local.yml` override.
`make build` just builds the images; `make prod-down` stops it.

## Ingress (Traefik)

Built-in Traefik labels; joins the homelab's external `proxy` network — no host
ports are published. On `${APP_HOST}`:

- `expense-api`  → `backend:8000`  for `PathPrefix(/api/)` + `/media`
- `expense-deploy` → `deploy-webhook:9000` for `PathPrefix(/hooks)` (priority 1500)
- `expense-app`  → `frontend:8080` for everything else (the SPA)

All on the `websecure` entrypoint with `tls=true` and the `default@file`
middleware (your Traefik file-provider defaults). Uncomment the
`certresolver=letsencrypt` labels if Traefik should fetch the certs. Requires an
external network named `proxy` — `docker network create proxy` once if missing.
Every service also sets `no-new-privileges` and json-file log rotation (shared
YAML anchors).

## Images

`.github/workflows/release.yml` builds & pushes on green CI (main) / `v*` tags:
`ghcr.io/<owner>/expense-diary-{backend,frontend}` tagged `latest`,
`sha-<commit>`, `semver`. The commit SHA is baked in (`GIT_SHA`, at `/api/v1/version`).

## Pull-deploy webhook (like cooking-jonelli)

1. On a green CI run on `main`, the release **deploy** job POSTs an
   **HMAC-SHA256-signed** `{sha, timestamp}` to `DEPLOY_WEBHOOK_URL`
   (`X-Hub-Signature-256`), verified against `DEPLOY_WEBHOOK_SECRET`.
2. Traefik routes `…/hooks/deploy` → `deploy-webhook:9000`; `deploy.sh` rejects
   stale/replayed timestamps (>5 min), takes a `flock`, logs in to GHCR
   (`GHCR_USER`/`GHCR_TOKEN`), sets `IMAGE_TAG=sha-<commit>` in `.env`, and runs
   `docker compose pull/up` **for the app services only** — over the
   **docker-socket-proxy** (least-privilege Docker API; the webhook has no raw
   socket), never touching itself or the proxy.
3. Not healthy → **auto-rollback** to the previous tag. Optional `ntfy` (`NTFY_URL`).

### Setup

1. Clone on the host (e.g. `/srv/expense`), create `.env` from `.env.example`
   (fill secrets — see the key-gen commands in the file — plus `GHCR_USER` /
   `GHCR_TOKEN` with a `read:packages` PAT and `APP_DEPLOY_DIR=/srv/expense`):
   ```bash
   docker network create proxy   # once, if it doesn't exist
   docker compose up -d          # brings up the app + webhook + socket proxy
   ```
2. GitHub repo **secrets**: `DEPLOY_WEBHOOK_URL` (`https://${APP_HOST}/hooks/deploy`)
   and `DEPLOY_WEBHOOK_SECRET` (matching `.env`). Without them the deploy job is a no-op.

**Security:** only the socket proxy sees the Docker socket (read-only, endpoint
allowlist). The `/hooks` route is public but HMAC-gated. For even tighter setups,
restrict the socket-proxy env flags further.
