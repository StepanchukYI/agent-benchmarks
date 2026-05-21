"""Per-server credentials store at ``$XDG_CONFIG_HOME/agent-benchmarks/credentials.json``."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from pydantic import BaseModel, ConfigDict

_FILENAME = "credentials.json"
_APP_DIR = "agent-benchmarks"


class Credentials(BaseModel):
    """OAuth token + GitHub identity tied to a single server_url."""

    model_config = ConfigDict(extra="ignore")

    access_token: str
    scope: str
    token_type: str
    github_login: str
    server_url: str
    expires_at: datetime | None = None


def _config_root() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return Path(base) / _APP_DIR
    return Path.home() / ".config" / _APP_DIR


def credentials_path() -> Path:
    return _config_root() / _FILENAME


def _normalize(server_url: str) -> str:
    return server_url.rstrip("/")


def _read_all() -> dict[str, dict]:
    path = credentials_path()
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(data, dict):
        return {}
    return data


def _write_all(data: dict[str, dict]) -> None:
    path = credentials_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2, default=str)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def load_credentials(server_url: str) -> Credentials | None:
    key = _normalize(server_url)
    blob = _read_all().get(key)
    if not blob:
        return None
    try:
        return Credentials.model_validate(blob)
    except Exception:
        return None


def save_credentials(creds: Credentials) -> None:
    data = _read_all()
    data[_normalize(creds.server_url)] = json.loads(creds.model_dump_json())
    _write_all(data)


def clear_credentials(server_url: str) -> None:
    data = _read_all()
    if data.pop(_normalize(server_url), None) is not None:
        _write_all(data)


__all__ = [
    "Credentials",
    "clear_credentials",
    "credentials_path",
    "load_credentials",
    "save_credentials",
]
