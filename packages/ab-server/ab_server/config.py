from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Server configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = "sqlite:///./ab.db"
    github_client_id: str = ""
    github_client_secret: str = ""
    session_secret: str = ""
    github_api_base: str = "https://api.github.com"
    github_device_base: str = "https://github.com"
    session_ttl_seconds: int = 60 * 60 * 24 * 30
    fetch_interval_sec: int = 60 * 15
    fetcher_cache_dir: str = str(Path.home() / ".cache" / "agent-benchmarks" / "fetcher")
    datasets_root: str = ""
    ab_test_auth: bool = False
    # Production marker. When true, create_app() refuses to start if
    # ab_test_auth is also true — the X-Test-User bypass must never be
    # reachable in production. Env var: IS_PRODUCTION.
    is_production: bool = False

    # Production hardening knobs (see ab_server/main.py:create_app).
    # Comma-separated origins for CORS. Default preserves local dev (Vite on 5173).
    allowed_origins: str = "http://localhost:5173"
    # Trust X-Forwarded-* headers (only enable when behind a reverse proxy you control).
    # Env var: AB_TRUST_PROXY (matches infra/.env.example and the codebase's AB_ convention).
    ab_trust_proxy: bool = False
    # Comma-separated list of peer IPs whose X-Forwarded-* headers Starlette's
    # ProxyHeadersMiddleware will honour when ab_trust_proxy is True. Default
    # 127.0.0.1 (localhost only) — tighten in prod to just the proxy's address
    # or range. Was previously hard-coded to "*", which allowed any container
    # on the docker bridge to spoof X-Forwarded-For and bypass per-IP rate
    # limiting.
    proxy_trusted_hosts: str = "127.0.0.1"
    # Token-bucket per-IP, in-memory. 0 disables. Single-instance only —
    # multi-instance deployments need a shared store (Redis), out of scope here.
    rate_limit_per_minute: int = 120
    # Max number of submissions to rescore inline per /repos/{id}/sync call.
    # Sync is synchronous and rescoring is CPU-bound; without a cap a repo
    # with 50+ new submissions parks a worker for the duration. The leftover
    # submissions get picked up on subsequent syncs (eventually consistent).
    sync_rescore_batch_size: int = 5
    # Background fetcher queue poller. 0 disables the poller entirely
    # (jobs still enqueue, just don't drain until something else calls
    # ab_server.fetcher.queue.run_one). Single-leader: do not enable on
    # more than one instance until claim is moved to a row-leased model.
    fetch_queue_poll_interval_sec: int = 30
    fetch_queue_enabled: bool = True
    # "text" (human-friendly) or "json" (one-line JSON per record).
    log_format: str = "text"

    # SMTP for alert email channel. Empty smtp_host disables email delivery
    # (channels of type "email" are skipped with a warning). All other knobs
    # are mainstream SMTP defaults; smtp_starttls is honored only when
    # smtp_use_ssl is False (RFC 3207).
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_ssl: bool = False
    smtp_starttls: bool = True
