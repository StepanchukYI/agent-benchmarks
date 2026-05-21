"""Local registry of repos per server, used by ``ab publish``."""

from __future__ import annotations

import json
import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from .credentials import _config_root

_FILENAME = "repos.json"


class RegisteredRepo(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    repo_url: str
    default_branch: str


def repos_path() -> Path:
    return _config_root() / _FILENAME


def _normalize(server_url: str) -> str:
    return server_url.rstrip("/")


def _read_all() -> dict[str, list[dict]]:
    path = repos_path()
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


def _write_all(data: dict[str, list[dict]]) -> None:
    path = repos_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, indent=2)
        fh.write("\n")
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)
    os.chmod(path, 0o600)


def list_repos(server_url: str) -> list[RegisteredRepo]:
    blobs = _read_all().get(_normalize(server_url), [])
    out: list[RegisteredRepo] = []
    for b in blobs:
        try:
            out.append(RegisteredRepo.model_validate(b))
        except Exception:
            continue
    return out


def add_repo(server_url: str, repo: RegisteredRepo) -> None:
    data = _read_all()
    key = _normalize(server_url)
    existing = data.get(key, [])
    deduped = [r for r in existing if r.get("repo_url") != repo.repo_url]
    deduped.append(json.loads(repo.model_dump_json()))
    data[key] = deduped
    _write_all(data)


__all__ = ["RegisteredRepo", "add_repo", "list_repos", "repos_path"]
