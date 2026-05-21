"""Read and write the metadata.yaml file inside a run dir."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    """Serialise metadata to YAML at the given path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(metadata, fh, sort_keys=False, allow_unicode=True)


def read_metadata(path: Path) -> dict[str, Any]:
    """Load metadata.yaml as a dict."""
    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"metadata.yaml must be a mapping at {path}")
    return loaded
