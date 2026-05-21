#!/bin/sh
# ab-server production entrypoint.
# 1. Wait for Postgres to accept connections (max 60s).
# 2. Apply Alembic migrations.
# 3. Exec gunicorn with the uvicorn worker class.
set -eu

log() { printf '[entrypoint] %s\n' "$*" >&2; }

# ---------------------------------------------------------------------------
# Parse host/port out of $DATABASE_URL so we can use pg_isready.
# Accepts forms like:
#   postgresql+psycopg://user:pass@host:5432/db
#   postgresql://user:pass@host/db
# Falls back to host=postgres port=5432 if parsing fails.
# ---------------------------------------------------------------------------
parse_db() {
    url="${DATABASE_URL:-}"
    if [ -z "$url" ]; then
        DB_HOST="postgres"
        DB_PORT="5432"
        return
    fi
    # Strip scheme.
    rest="${url#*://}"
    # Strip optional userinfo.
    case "$rest" in
        *"@"*) rest="${rest#*@}" ;;
    esac
    # Strip path/query.
    hostport="${rest%%/*}"
    hostport="${hostport%%\?*}"
    case "$hostport" in
        *":"*)
            DB_HOST="${hostport%%:*}"
            DB_PORT="${hostport##*:}"
            ;;
        *)
            DB_HOST="$hostport"
            DB_PORT="5432"
            ;;
    esac
    [ -n "$DB_HOST" ] || DB_HOST="postgres"
    [ -n "$DB_PORT" ] || DB_PORT="5432"
}

wait_for_db() {
    parse_db
    log "waiting for postgres at ${DB_HOST}:${DB_PORT} ..."
    i=0
    while [ "$i" -lt 60 ]; do
        if pg_isready -h "$DB_HOST" -p "$DB_PORT" -q; then
            log "postgres is ready (after ${i}s)"
            return 0
        fi
        i=$((i + 1))
        sleep 1
    done
    log "ERROR: postgres at ${DB_HOST}:${DB_PORT} did not become ready in 60s"
    return 1
}

run_migrations() {
    log "running alembic upgrade head ..."
    # alembic.ini lives in packages/ab-server with script_location = alembic
    # and prepend_sys_path = . — so we must cd in.
    cd /app/packages/ab-server
    alembic upgrade head
    cd /app
    log "migrations applied"
}

main() {
    if [ "${AB_SKIP_DB_WAIT:-0}" != "1" ]; then
        wait_for_db
    fi
    if [ "${AB_SKIP_MIGRATIONS:-0}" != "1" ]; then
        run_migrations
    fi

    workers="${GUNICORN_WORKERS:-4}"
    timeout="${GUNICORN_TIMEOUT:-60}"

    # Bind address. Default 0.0.0.0:8000 because in this Docker topology Caddy
    # runs in a separate container and must reach us across the ab_net bridge;
    # 127.0.0.1 would make us unreachable. Override only if you understand the
    # topology (e.g. host-network deployments).
    bind="${GUNICORN_BIND:-0.0.0.0:8000}"

    # Which peer IPs we trust to set X-Forwarded-* headers. Was '*' which lets
    # ANY container on the same docker network spoof X-Forwarded-For and bypass
    # per-IP rate limiting. Default to RFC1918 + localhost so only same-network
    # proxies (Caddy in 172.16.0.0/12) are trusted. Override at deploy time if
    # your topology differs.
    forwarded_allow_ips="${GUNICORN_FORWARDED_ALLOW_IPS:-127.0.0.1,172.16.0.0/12,10.0.0.0/8,192.168.0.0/16}"

    log "starting gunicorn with ${workers} workers, timeout ${timeout}s, bind ${bind}"
    log "trusting forwarded headers from: ${forwarded_allow_ips}"

    exec gunicorn ab_server.main:app \
        -k uvicorn.workers.UvicornWorker \
        -w "${workers}" \
        -b "${bind}" \
        --access-logfile - \
        --error-logfile - \
        --timeout "${timeout}" \
        --graceful-timeout 30 \
        --forwarded-allow-ips="${forwarded_allow_ips}"
}

main "$@"
