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

    # Production hardening knobs (see ab_server/main.py:create_app).
    # Comma-separated origins for CORS. Default preserves local dev (Vite on 5173).
    allowed_origins: str = "http://localhost:5173"
    # Trust X-Forwarded-* headers (only enable when behind a reverse proxy you control).
    # Env var: AB_TRUST_PROXY (matches infra/.env.example and the codebase's AB_ convention).
    ab_trust_proxy: bool = False
    # Token-bucket per-IP, in-memory. 0 disables. Single-instance only —
    # multi-instance deployments need a shared store (Redis), out of scope here.
    rate_limit_per_minute: int = 120
    # "text" (human-friendly) or "json" (one-line JSON per record).
    log_format: str = "text"
