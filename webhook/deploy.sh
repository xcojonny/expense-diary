#!/bin/bash
# Pull-deploy, triggered by the HMAC-signed webhook with (sha, timestamp):
#   deploy.sh <git-sha> <unix-timestamp> [--skip-migrate]
#
# - Replay protection: requests older/newer than 5 min are rejected (the HMAC
#   signature also covers the timestamp, so it can't be forged).
# - flock: concurrent deploys are serialized.
# - Auto-rollback: if the new state isn't healthy, the previous IMAGE_TAG is
#   restored (backend/worker/frontend only — the DB may already be migrated).
# - --skip-migrate: for manual rollbacks to an older SHA (the old image doesn't
#   know the newer Alembic revision; migrations are expand-contract).
set -euo pipefail

SHA="${1:?usage: deploy.sh <sha> <timestamp> [--skip-migrate]}"
TS="${2:?missing timestamp}"
SKIP_MIGRATE="${3:-}"
COMPOSE_DIR="${COMPOSE_DIR:-/srv/expense}"
LOCK_FILE="/tmp/expense-deploy.lock"
MAX_AGE=300

notify() {
  local title="$1" body="$2" prio="${3:-default}"
  [ -n "${NTFY_URL:-}" ] || return 0
  curl -fsS -m 10 -H "Title: ${title}" -H "Priority: ${prio}" -d "${body}" "${NTFY_URL}" \
    >/dev/null || true
}

now=$(date +%s)
if [ $((now - TS)) -gt ${MAX_AGE} ] || [ $((TS - now)) -gt ${MAX_AGE} ]; then
  echo "REJECT: stale timestamp (${TS}, now ${now})" >&2
  notify "Deploy verworfen" "Veralteter Webhook-Aufruf (Replay-Schutz), sha=${SHA}" high
  exit 1
fi

if ! [[ "${SHA}" =~ ^[a-f0-9]{7,64}$ ]]; then
  echo "REJECT: invalid sha '${SHA}'" >&2
  exit 1
fi

exec 9>"${LOCK_FILE}"
if ! flock -w 120 9; then
  echo "REJECT: another deploy is running" >&2
  notify "Deploy übersprungen" "Anderes Deploy läuft noch, sha=${SHA}" high
  exit 1
fi

cd "${COMPOSE_DIR}"
if [ ! -f docker-compose.yml ] || [ ! -f .env ]; then
  echo "REJECT: ${COMPOSE_DIR} has no docker-compose.yml/.env — check the mount" >&2
  notify "Deploy fehlgeschlagen ❌" "Falsches Deploy-Verzeichnis: ${COMPOSE_DIR}" high
  exit 1
fi

PREVIOUS_TAG=$(grep -E '^IMAGE_TAG=' .env | cut -d= -f2 || true)
NEW_TAG="sha-${SHA}"

set_tag() {
  if grep -qE '^IMAGE_TAG=' .env; then
    sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=$1|" .env
  else
    echo "IMAGE_TAG=$1" >> .env
  fi
}

compose_up() {
  if [ "${SKIP_MIGRATE}" = "--skip-migrate" ]; then
    docker compose pull backend worker frontend
    docker compose up -d --wait --no-deps backend worker frontend
  else
    docker compose pull
    docker compose up -d --wait
  fi
}

echo "DEPLOY ${PREVIOUS_TAG:-<none>} -> ${NEW_TAG}"
set_tag "${NEW_TAG}"

if compose_up; then
  notify "Deploy erfolgreich ✅" "expense-diary @ ${NEW_TAG}"
  echo "OK ${NEW_TAG}"
  exit 0
fi

echo "DEPLOY FAILED — rolling back to ${PREVIOUS_TAG:-latest}" >&2
if [ -n "${PREVIOUS_TAG}" ] && [ "${PREVIOUS_TAG}" != "${NEW_TAG}" ]; then
  set_tag "${PREVIOUS_TAG}"
  if docker compose pull backend worker frontend \
     && docker compose up -d --wait --no-deps backend worker frontend; then
    notify "Deploy fehlgeschlagen — Rollback OK ⚠️" \
      "expense-diary: ${NEW_TAG} wurde nicht healthy, zurück auf ${PREVIOUS_TAG}" high
    exit 1
  fi
fi
notify "Deploy fehlgeschlagen ❌" \
  "expense-diary: ${NEW_TAG} nicht healthy und Rollback nicht möglich — manuell eingreifen!" max
exit 1
