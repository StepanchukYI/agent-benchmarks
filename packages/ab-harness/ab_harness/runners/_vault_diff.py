"""Snapshot + diff a workdir by sha256, used to record vault_state_diff per turn."""

from __future__ import annotations

import hashlib
from pathlib import Path

_MAX_BYTES = 5 * 1024 * 1024
_EXCLUDED_DIRS = frozenset({".git", ".venv", "node_modules", "__pycache__", ".pytest_cache"})


def _iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in _EXCLUDED_DIRS for part in path.relative_to(root).parts):
            continue
        try:
            if path.stat().st_size > _MAX_BYTES:
                continue
        except OSError:
            continue
        yield path


def _hash_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def snapshot(workdir: str | Path) -> dict[str, str]:
    root = Path(workdir)
    if not root.exists():
        return {}
    out: dict[str, str] = {}
    for path in _iter_files(root):
        rel = str(path.relative_to(root))
        try:
            out[rel] = _hash_file(path)
        except OSError:
            continue
    return out


def diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    before_keys = set(before)
    after_keys = set(after)
    created = sorted(after_keys - before_keys)
    deleted = sorted(before_keys - after_keys)
    modified = sorted(k for k in before_keys & after_keys if before[k] != after[k])
    return {"created": created, "modified": modified, "deleted": deleted}
