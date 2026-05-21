# Restore from backup

Restoring a Postgres dump produced by `scripts/db-backup.sh`. Destructive — overwrites the current database.

If you just want to run the helper: `CONFIRM=yes ./scripts/db-restore.sh path/to/ab_YYYYMMDDTHHMMSSZ.sql.gz`. The manual steps below are what the script does, in case you need to do it by hand.

## Prerequisites

- The compose stack is up, or at least Postgres is reachable from the host (`docker compose ps postgres` shows `running (healthy)`).
- The backup file is on disk and unaltered. `gzip -t backup.sql.gz` should exit 0.

## Steps (manual)

```bash
COMPOSE="docker compose -f infra/docker-compose.prod.yml"

# 1. Stop ab-server only; leave Postgres up.
$COMPOSE stop ab-server

# 2. Drop and recreate the target database.
$COMPOSE exec -T postgres psql -U ab -d postgres -v ON_ERROR_STOP=1 <<SQL
DROP DATABASE IF EXISTS ab;
CREATE DATABASE ab OWNER ab;
SQL

# 3. Restore the dump.
gunzip -c backup_2026-05-21.sql.gz | $COMPOSE exec -T postgres psql -U ab -d ab -v ON_ERROR_STOP=1

# 4. Restart ab-server. Entrypoint will run `alembic upgrade head` —
#    no-op if the dump already includes the current schema.
$COMPOSE start ab-server
```

## Verify

```bash
curl -fsS https://${AB_DOMAIN}/healthz
# → {"status":"ok"}

# Spot-check that data is back. Replace <route> with whatever you actually had:
curl -fsS https://${AB_DOMAIN}/api/v1/leaderboard | jq '.runs | length'
```

In the browser, sign in and confirm runs/repos/submissions are visible. If the leaderboard is empty but the API returns rows, hard-reload the SPA — it's a client-side cache.

## If the restore fails halfway through

Postgres aborts on the first error because of `-v ON_ERROR_STOP=1`. The database is now in an inconsistent state. Recover by running the drop/recreate step again, then re-run the restore — or restore from an older backup. Don't try to "patch" a half-restored DB.

## Recovery time

For a friends-first deploy with a few thousand rows, a full restore from a gzipped dump takes well under a minute. If you ever cross into multi-minute restore territory, switch to `pg_dump --format=custom` and `pg_restore -j N` — but you won't need this until the data is much bigger than what this project is sized for.
