#!/bin/sh
# db-backup.sh — pg_dump the agent-benchmarks Postgres into a gzipped file,
# then prune backups older than $RETENTION_DAYS.
#
# Env overrides:
#   BACKUP_DIR       where to write backups       (default: $HOME/agent-benchmarks-backups)
#   RETENTION_DAYS   prune older than N days      (default: 30)
#   COMPOSE          docker compose invocation    (default: docker compose -f infra/docker-compose.prod.yml)
#   PG_USER          postgres role                (default: ab)
#   PG_DB            postgres database name       (default: ab)
#
# Run from the repo root, e.g. via cron:
#   5 3 * * * cd /opt/agent-benchmarks && ./scripts/db-backup.sh >> /var/log/ab-backup.log 2>&1
set -eu

BACKUP_DIR="${BACKUP_DIR:-$HOME/agent-benchmarks-backups}"
RETENTION_DAYS="${RETENTION_DAYS:-30}"
COMPOSE="${COMPOSE:-docker compose -f infra/docker-compose.prod.yml}"
PG_USER="${PG_USER:-ab}"
PG_DB="${PG_DB:-ab}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT="$BACKUP_DIR/ab_$STAMP.sql.gz"

# -T disables TTY allocation so this works under cron.
$COMPOSE exec -T postgres pg_dump -U "$PG_USER" -d "$PG_DB" | gzip > "$OUT"

echo "wrote $OUT ($(du -h "$OUT" | cut -f1))"

# Prune old backups. -mtime +N matches files modified more than N days ago.
find "$BACKUP_DIR" -name 'ab_*.sql.gz' -mtime +"$RETENTION_DAYS" -delete
