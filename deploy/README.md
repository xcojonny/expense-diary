# Deployment

Two compose stacks:

- **App** (`docker-compose.yml`): db, redis, one-shot `migrate`, backend, worker,
  frontend. Configure via `.env` (template: `.env.example`). `IMAGE_TAG` selects
  which GHCR image tag runs — the deploy webhook flips it to `sha-<commit>`.
- **Infra** (`infra/docker-compose.infra.yml`): the pull-deploy webhook.

### Ingress (Traefik)

The stack ships **Traefik labels** and joins the homelab's existing external
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

`infra/webhook/` is a tiny [`webhook`](https://github.com/adnanh/webhook) service:

1. On a green CI run on `main`, the release workflow's **deploy** job POSTs an
   **HMAC-SHA256-signed** `{sha, timestamp}` body to `DEPLOY_WEBHOOK_URL`
   (`X-Hub-Signature-256`), verified against `DEPLOY_WEBHOOK_SECRET`.
2. `deploy.sh` validates the signature (via `webhook`), rejects stale/replayed
   timestamps (>5 min), takes a `flock`, sets `IMAGE_TAG=sha-<commit>` in the
   app `.env`, and runs `docker compose pull && up -d --wait`.
3. If the new state isn't healthy it **auto-rolls-back** to the previous tag.
4. Optional `ntfy` notifications (`NTFY_URL`).

### Setup

1. Deploy the app stack once (`docker compose up -d` in this directory).
2. Run the infra stack on the same host:
   ```bash
   cd infra
   # .env: DEPLOY_WEBHOOK_SECRET=<random>, APP_DEPLOY_DIR=/abs/path/to/deploy, NTFY_URL=…
   docker compose -f docker-compose.infra.yml up -d --build
   ```
   Expose `https://deploy.example.org/hooks/deploy` via your proxy (TLS).
3. Add GitHub repo **secrets**: `DEPLOY_WEBHOOK_URL`
   (`https://deploy.example.org/hooks/deploy`) and `DEPLOY_WEBHOOK_SECRET`
   (matching the infra `.env`). Without them the deploy job is a no-op.

**Security:** the webhook mounts the Docker socket — keep it internal, TLS-only,
and consider fronting it with `tecnativa/docker-socket-proxy` for least privilege.
