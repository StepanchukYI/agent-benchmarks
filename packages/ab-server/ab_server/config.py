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
