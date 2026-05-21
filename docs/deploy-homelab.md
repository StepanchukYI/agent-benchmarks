# Self-hosting agent-benchmarks on a homelab

Single-host docker-compose deployment behind Caddy with auto-TLS. Target audience: one maintainer running this on a Linux box at home.

If you want a managed multi-tenant deploy, this isn't it — see the build spec instead.

## Stack

- `postgres` — Postgres 16, single instance, named volume.
- `ab-server` — FastAPI, gunicorn behind Caddy.
- `ab-leaderboard` — React SPA, served as static files.
- `caddy` — reverse proxy + auto-TLS (Let's Encrypt for public hostnames, self-signed for `.local`).

Compose file: `infra/docker-compose.prod.yml`. Network: `ab_net`. Volumes: `ab_pgdata`, `ab_fetcher_cache`, `caddy_data`, `caddy_config`.

## Prerequisites

- Linux box (Ubuntu 22.04 / 24.04 or Debian 12 tested). 2 vCPU + 4 GB RAM is fine for friends-first traffic.
- Docker Engine 24+ and the Docker Compose v2 plugin. `docker compose version` must print v2.x.
- DNS:
  - **Public**: `ab.example.com` A/AAAA → homelab public IP. Ports 80 + 443 forwarded to the box.
  - **LAN-only**: a name that resolves on your LAN (e.g. `ab.local` via mDNS, or a record in your local DNS). Caddy will self-sign.
- GitHub OAuth App. Create at https://github.com/settings/developers → "New OAuth App":
  - Homepage URL: `https://${AB_DOMAIN}`
  - Authorization callback URL: `https://${AB_DOMAIN}/api/v1/auth/github/callback`
  - Save the **Client ID** and generate a **Client Secret** — you only see the secret once.

## Initial setup (one-time)

```bash
git clone git@github.com:StepanchukYI/agent-benchmarks.git /opt/agent-benchmarks
cd /opt/agent-benchmarks
cp infra/.env.example .env
```

Edit `.env`:

| Var | Value |
|---|---|
| `POSTGRES_PASSWORD` | strong random string (`openssl rand -hex 24`) |
| `DATABASE_URL` | `postgresql+psycopg://ab:${POSTGRES_PASSWORD}@postgres:5432/ab` |
| `GITHUB_CLIENT_ID` | from your GitHub OAuth App |
| `GITHUB_CLIENT_SECRET` | from your GitHub OAuth App |
| `SESSION_SECRET` | `openssl rand -hex 32` |
| `AB_DOMAIN` | e.g. `ab.example.com` |
| `AB_API_BASE_URL` | `https://${AB_DOMAIN}/api/v1` |
| `ALLOWED_ORIGINS` | `https://${AB_DOMAIN}` |
| `AB_TRUST_PROXY` | `1` (Caddy sets `X-Forwarded-*`) |
| `RATE_LIMIT_PER_MINUTE` | `60` is a sensible start |
| `LOG_FORMAT` | `json` |
| `GUNICORN_WORKERS` | `2` for 2 vCPU; bump to `4` if you have more |

`chmod 600 .env` — it holds secrets.

## Bring it up

```bash
docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --build
docker compose -f infra/docker-compose.prod.yml logs -f ab-server
```

First boot order:

1. Postgres comes up, healthcheck passes.
2. `ab-server` entrypoint waits on the Postgres healthcheck, runs `alembic upgrade head`, then starts gunicorn.
3. `ab-leaderboard` serves the prebuilt SPA bundle.
4. Caddy starts, requests a Let's Encrypt cert for `${AB_DOMAIN}` (or generates a self-signed cert for `.local`). First cert issuance can take 30–90 seconds.

## Deploy from pre-built images

The `build-images` GitHub Actions workflow publishes both runtime images to GHCR on every push to `main` and on every `v*` tag. The deploy machine can pull them instead of building from source — no toolchain, no `pnpm`, no `uv` needed on the host. Only Docker + Compose v2.

Images published:

- `ghcr.io/stepanchukyi/agent-benchmarks-ab-server:<tag>`
- `ghcr.io/stepanchukyi/agent-benchmarks-ab-leaderboard:<tag>`

Available tags:

| Tag | When published | Use for |
|---|---|---|
| `sha-<git_sha>` | every build | **Pin this in prod.** Immutable, reproducible. |
| `v0.X.Y` | on tag push (`v*`) | Stable release channel. |
| `main` | push to `main` | Auto-update channel — `docker compose pull` redeploys. |
| `latest` | push to `main` | Alias for `main` (NOT the latest release tag — be deliberate). |

### One-time setup on the deploy machine

You only need `infra/` on the host. The simplest paths:

```bash
# Option A — shallow clone (gets you scripts/db-backup.sh and friends too)
git clone --depth 1 https://github.com/StepanchukYI/agent-benchmarks.git /opt/agent-benchmarks
cd /opt/agent-benchmarks

# Option B — copy just infra/ from a workstation
# scp -r infra/ deploy-host:/opt/agent-benchmarks/

cp infra/.env.example /opt/agent-benchmarks/infra/.env
chmod 600 /opt/agent-benchmarks/infra/.env
```

Edit `infra/.env`. In addition to the secrets listed under "Initial setup" above, set:

| Var | Value |
|---|---|
| `IMAGE_OWNER` | `stepanchukyi` (lowercase GHCR owner) |
| `IMAGE_TAG` | `sha-<git_sha>` for a pinned prod build, or `main` for auto-update |

If the GitHub repo/packages are public (default for this project), no `docker login` is needed. If they are private, run once:

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u <github-user> --password-stdin
```

### Pull and run

```bash
cd /opt/agent-benchmarks
docker compose -f infra/docker-compose.deploy.yml --env-file infra/.env pull
docker compose -f infra/docker-compose.deploy.yml --env-file infra/.env up -d
docker compose -f infra/docker-compose.deploy.yml --env-file infra/.env logs -f ab-server
```

### Update to a new build

```bash
# Update the tag in infra/.env, then:
docker compose -f infra/docker-compose.deploy.yml --env-file infra/.env pull
docker compose -f infra/docker-compose.deploy.yml --env-file infra/.env up -d
# Old containers stop, new ones start. Migrations run automatically in the
# ab-server entrypoint.
```

### Recommended workflow

- **Production:** pin `IMAGE_TAG=sha-<commit_sha>` (or `IMAGE_TAG=v0.X.Y`). Bump deliberately. Roll back by setting `IMAGE_TAG` to a previous sha and re-running `pull` + `up -d`.
- **Staging/homelab:** `IMAGE_TAG=main` is fine. A daily cron of `compose pull && compose up -d` gives you auto-update.

### Where to find the right `sha-<git_sha>`

Either:

- Look at the most recent successful run of the `build-images` workflow under Actions; the digest is printed in the job log.
- `git rev-parse origin/main` on a workstation that has the repo.
- The `scripts/release.sh` helper prints the expected URLs for a tag.

First boot from pulled images follows the same order as a build-from-source boot (Postgres → server migrations → leaderboard → Caddy).

## Verify

```bash
# Health check
curl -fsS https://${AB_DOMAIN}/healthz
# → {"status":"ok"}

# SPA loads
curl -fsSI https://${AB_DOMAIN}/ | head -1
# → HTTP/2 200
```

In a browser:

1. Open `https://${AB_DOMAIN}` — leaderboard SPA loads with an empty state.
2. Click "Sign in with GitHub" — completes the OAuth flow.
3. Run `ab register` from a client to add your results repo (see top-level README).

## Daily ops

```bash
# Tail server logs (structured JSON; pipe through jq if you like)
docker compose -f infra/docker-compose.prod.yml logs -f ab-server | jq

# Tail Caddy access log
docker compose -f infra/docker-compose.prod.yml logs -f caddy

# Restart server only (e.g. after rotating SESSION_SECRET)
docker compose -f infra/docker-compose.prod.yml restart ab-server

# Pull updates and redeploy
git pull
docker compose -f infra/docker-compose.prod.yml up -d --build
# Migrations run automatically in the ab-server entrypoint.

# Stop everything
docker compose -f infra/docker-compose.prod.yml down

# Stop and wipe the database (DESTRUCTIVE)
docker compose -f infra/docker-compose.prod.yml down -v
```

## Backups

A `pg_dump` wrapper lives at `scripts/db-backup.sh`. It writes gzipped dumps to `$BACKUP_DIR` (default `~/agent-benchmarks-backups`) and prunes anything older than `$RETENTION_DAYS` (default 30).

Recommended cron entry — daily at 03:05 UTC:

```cron
5 3 * * * cd /opt/agent-benchmarks && ./scripts/db-backup.sh >> /var/log/ab-backup.log 2>&1
```

If you want offsite copies, layer rclone/restic/borg on top of the same `$BACKUP_DIR`. Out of scope here.

## Restore

See [`restore-from-backup.md`](restore-from-backup.md). Short version: stop `ab-server`, drop+recreate the DB, stream the gzipped dump through `psql`, restart `ab-server`. The `scripts/db-restore.sh` helper does this for you.

## Updating the GitHub OAuth callback

If you rename `AB_DOMAIN` (or move from `.local` to a public domain):

1. Update the OAuth App callback URL at https://github.com/settings/developers to match.
2. Update `AB_DOMAIN`, `AB_API_BASE_URL`, `ALLOWED_ORIGINS` in `.env`.
3. `docker compose -f infra/docker-compose.prod.yml up -d` — Caddy reloads its config, server picks up new env on restart.

If you regenerate the OAuth secret on GitHub, swap `GITHUB_CLIENT_SECRET` in `.env` and `restart ab-server`.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `alembic upgrade head` fails on startup | `DATABASE_URL` wrong, or Postgres still booting | Check `.env`. Compose `depends_on: service_healthy` should prevent the race — if you see it, inspect `docker compose logs postgres`. |
| Caddy can't issue Let's Encrypt cert | DNS not propagated, or ports 80/443 not reachable | `dig ${AB_DOMAIN}` from outside the LAN. Confirm router port-forwards 80+443 to the box. Caddy retries automatically — give it a few minutes. |
| OAuth callback returns 404 | Callback URL on GitHub doesn't match `${AB_DOMAIN}/api/v1/auth/github/callback` | Fix it in the GitHub OAuth App settings, then sign in again. |
| `429 Too Many Requests` | `RATE_LIMIT_PER_MINUTE` is too tight | Raise it in `.env`, `restart ab-server`. |
| Browser shows cert warning on `.local` | Self-signed cert (expected for `.local`) | Add Caddy's root to your trust store, or accept the warning once per device. |
| `ab-server` restarts in a loop | Usually a config error | `docker compose logs ab-server` — the gunicorn / alembic error is in the last 50 lines. |
| `502 Bad Gateway` from Caddy | `ab-server` is down or not yet healthy | `docker compose ps`, then `logs ab-server`. |
| Disk filling up | Old backups, container logs, or fetcher cache | Check `~/agent-benchmarks-backups` retention and `docker system df`. `docker system prune --volumes` is safe **only** if you understand what it removes. |

## What you should monitor

Bare minimum for a friends-first deploy:

- `curl https://${AB_DOMAIN}/healthz` from a separate uptime checker (UptimeRobot free tier or your own cron).
- Disk usage on the volume that holds `ab_pgdata` and the backup directory.
- That `db-backup.sh` actually ran in the last 24h — easy to check: newest file in `$BACKUP_DIR`.

Anything fancier (Prometheus, Grafana, alerting) is out of scope for this guide.
