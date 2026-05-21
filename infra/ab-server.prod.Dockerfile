# syntax=docker/dockerfile:1.7
# Production image for ab-server.
# Multi-stage: builder resolves and installs deps with uv into a venv,
# runtime carries only the venv + app code on a slim base.

############################
# Stage 1: builder
############################
FROM python:3.11-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Build-only deps. libpq-dev is needed if psycopg falls back from binary;
# build-essential covers any C extension. Both are dropped from the runtime stage.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

# uv pinned via the official binary install.
RUN pip install --no-cache-dir uv

WORKDIR /app

# Workspace metadata first for better layer caching.
COPY pyproject.toml uv.lock* ./
COPY packages ./packages

# Install all workspace runtime dependencies, but drop the `dev` group
# (pytest/mypy/ruff/debugpy/...).
# We install all workspace members because ab-server imports cross-package
# (e.g. ab_harness.scorers.privacy_check) without declaring those as
# explicit dependencies. Until that's cleaned up, --all-packages is required
# for the import graph to resolve at runtime.
RUN uv sync --frozen --no-dev --all-packages \
    || uv sync --no-dev --all-packages

# Add gunicorn into the resolved venv WITHOUT touching the lockfile.
# uvicorn[standard] is already a transitive dep of ab-server.
RUN uv pip install --python /app/.venv/bin/python --no-cache "gunicorn>=21.2"

############################
# Stage 2: runtime
############################
FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH" \
    VIRTUAL_ENV=/app/.venv \
    PYTHONPATH=/app/packages/ab-server

# Runtime-only OS deps:
# - libpq5: shared library psycopg needs at runtime
# - postgresql-client: provides pg_isready used by the entrypoint
# - curl: healthcheck probe
# - ca-certificates: outbound TLS (GitHub API, etc.)
# Build tools and git are intentionally absent from the runtime image.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libpq5 \
        postgresql-client \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 ab \
    && useradd --system --uid 10001 --gid ab --home-dir /app --shell /usr/sbin/nologin ab

WORKDIR /app

# Copy the resolved venv.
COPY --from=builder /app/.venv /app/.venv

# Copy app sources. We keep the workspace shape so alembic resolves
# `script_location = alembic` relative to packages/ab-server.
COPY pyproject.toml uv.lock* ./
COPY packages ./packages
COPY infra/entrypoint-server.sh /app/infra/entrypoint-server.sh

# Cache dir for the fetcher; declared in compose as a volume mount.
RUN mkdir -p /app/.cache /app/.cache/agent-benchmarks/fetcher \
    && chmod +x /app/infra/entrypoint-server.sh \
    && chown -R ab:ab /app

USER ab

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -fsS http://localhost:8000/healthz || exit 1

ENTRYPOINT ["/app/infra/entrypoint-server.sh"]
