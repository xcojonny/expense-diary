# Deployment

All deploy files live at the repo root, so on the server it's just
`git pull && docker compose pull && docker compose up -d`.

Three compose stacks (root):

- **App** (`docker-compose.yml`): db, redis, one-shot `migrate`, backend, worker,
  frontend. Configure via `.env` (template: `.env.example`). `IMAGE_TAG` selects
  which GHCR image tag runs — the deploy webhook flips it to `sha-<commit>`.
- **Webhook** (`docker-compose.infra.yml`, source in `webhook/`): the pull-deploy webhook.
- **Dev infra** (`docker-compose.dev.yml`): Postgres + Redis for local dev only.

> On the server `docker compose …` (no `-f`) targets `docker-compose.yml` (the app).

## Ingress (Traefik)

The app stack ships **Traefik labels** and joins the homelab's existing external
`proxy` network — no host ports are published. On the public host `${APP_HOST}`:

- router `expense-api` → `backend:8000` for `PathPrefix(/api/)` and `/media`
- router `expense-app` → `frontend:8080` for everything else (the SPA)

Both use the `websecure` entrypoint with `tls=true` and the `default@file`
middleware (your Traefik file-provider security defaults). Uncomment the
`certresolver=letsencrypt` label (or keep `tls=true` if certs come from
elsewhere). Requires an external Traefik network named `proxy`:
`docker network create proxy` (once) if it doesn't exist. Not using Traefik?
Replace the labels with a `ports:` mapping and your own proxy.

## Images

`.github/workflows/release.yml` builds & pushes on green CI (main) / `v*` tags:

- `ghcr.io/<owner>/expense-diary-backend`
- `ghcr.io/<owner>/expense-diary-frontend`

tagged `latest`, `sha-<commit>`, and `semver` on tags. The commit SHA is baked in
(`GIT_SHA`), visible at `/api/v1/version`.

## Pull-deploy webhook (like cooking-jonelli)

`webhook/` is a tiny [`webhook`](https://github.com/adnanh/webhook) service:

1. On a green CI run on `main`, the release workflow's **deploy** job POSTs an
   **HMAC-SHA256-signed** `{sha, timestamp}` body to `DEPLOY_WEBHOOK_URL`
   (`X-Hub-Signature-256`), verified against `DEPLOY_WEBHOOK_SECRET`.
2. `deploy.sh` validates the signature (via `webhook`), rejects stale/replayed
   timestamps (>5 min), takes a `flock`, sets `IMAGE_TAG=sha-<commit>` in the
   root `.env`, and runs `docker compose pull && up -d --wait`.
3. If the new state isn't healthy it **auto-rolls-back** to the previous tag.
4. Optional `ntfy` notifications (`NTFY_URL`).

### Setup

1. Clone the repo on the host (e.g. to `/srv/expense`), create `.env` from
   `.env.example`, and deploy the app stack once:
   ```bash
   docker network create proxy   # once, if it doesn't exist
   docker compose up -d
   ```
2. Run the webhook stack from the same directory (it shares the root `.env`;
   set `DEPLOY_WEBHOOK_SECRET` and `APP_DEPLOY_DIR=/srv/expense`):
   ```bash
   docker compose -f docker-compose.infra.yml up -d --build
   ```
   Expose `https://deploy.example.org/hooks/deploy` via your proxy (TLS).
3. Add GitHub repo **secrets**: `DEPLOY_WEBHOOK_URL`
   (`https://deploy.example.org/hooks/deploy`) and `DEPLOY_WEBHOOK_SECRET`
   (matching the root `.env`). Without them the deploy job is a no-op.

**Security:** the webhook mounts the Docker socket — keep it internal, TLS-only,
and consider fronting it with `tecnativa/docker-socket-proxy` for least privilege.
