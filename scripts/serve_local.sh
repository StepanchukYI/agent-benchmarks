#!/usr/bin/env bash
# serve_local.sh — boot the backend + frontend for local browsing.
#
#   scripts/serve_local.sh           # both, foreground (Ctrl-C to stop)
#   API_ONLY=1 scripts/serve_local.sh
#   FE_ONLY=1  scripts/serve_local.sh
#
# Backend: SQLite at packages/ab-server/ab.db, AB_TEST_AUTH=1 (dev only).
# Frontend: pnpm dev on :5173 reading AB_API_BASE_URL from .env.local.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

start_api() {
  cd "$REPO_ROOT/packages/ab-server"
  DATABASE_URL="sqlite:///$(pwd)/ab.db" \
  AB_TEST_AUTH=1 \
    uv run uvicorn ab_server.main:app --port 8000 --host 127.0.0.1
}

start_fe() {
  cd "$REPO_ROOT/packages/ab-leaderboard"
  pnpm dev --host 127.0.0.1 --port 5173
}

if [[ "${API_ONLY:-0}" = "1" ]]; then
  start_api
elif [[ "${FE_ONLY:-0}" = "1" ]]; then
  start_fe
else
  start_api &
  api_pid=$!
  trap 'kill $api_pid 2>/dev/null || true' EXIT
  sleep 2
  start_fe
fi
