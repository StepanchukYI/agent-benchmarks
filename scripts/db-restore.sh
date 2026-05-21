#!/bin/sh
# db-restore.sh — restore the agent-benchmarks Postgres from a gzipped pg_dump.
#
# Usage:
#   ./scripts/db-restore.sh path/to/ab_YYYYMMDDTHHMMSSZ.sql.gz
#
# What this does:
#   1. Stops ab-server (Postgres stays up).
#   2. Drops and recreates the target database.
#   3. Streams the gzipped dump into psql.
#   4. Restarts ab-server.
#
# Env overrides:
#   COMPOSE   docker compose invocation (default: docker compose -f infra/docker-compose.prod.yml)
#   PG_USER   postgres role             (default: ab)
#   PG_DB     postgres database name    (default: ab)
#
# This is destructive. The script will refuse to run unless CONFIRM=yes.
set -eu

if [ "$#" -ne 1 ]; then
  echo "usage: $0 <backup.sql.gz>" >&2
  exit 2
fi

BACKUP_FILE="$1"
COMPOSE="${COMPOSE:-docker compose -f infra/docker-compose.prod.yml}"
PG_USER="${PG_USER:-ab}"
PG_DB="${PG_DB:-ab}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "error: $BACKUP_FILE not found" >&2
  exit 1
fi

if [ "${CONFIRM:-}" != "yes" ]; then
  echo "This will DROP database '$PG_DB' and restore from $BACKUP_FILE."
  echo "Re-run with CONFIRM=yes to proceed, e.g.:"
  echo "  CONFIRM=yes $0 $BACKUP_FILE"
  exit 1
fi

echo "==> stopping ab-server"
$COMPOSE stop ab-server

echo "==> dropping and recreating database $PG_DB"
$COMPOSE exec -T postgres psql -U "$PG_USER" -d postgres -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS $PG_DB;
CREATE DATABASE $PG_DB OWNER $PG_USER;
SQL

echo "==> restoring from $BACKUP_FILE"
gunzip -c "$BACKUP_FILE" | $COMPOSE exec -T postgres psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1

echo "==> starting ab-server"
$COMPOSE start ab-server

echo "done. Verify with: curl -fsS https://\${AB_DOMAIN}/healthz"
