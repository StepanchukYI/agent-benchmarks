"""Read and write the metadata.yaml file inside a run dir."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict


class MetadataFile(BaseModel):
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    run_id: str
    task_id: str
    model: str
    tier: str
    tier_hash: str | None = None
    dataset_version: str
    harness: str
    started_at: datetime | str
    finished_at: datetime | str | None = None
    status: str | None = None
    prompt_template_hash: str | None = None


def write_metadata(path: Path, metadata: dict[str, Any]) -> None:
    """Validate against MetadataFile then serialise to YAML at the given path."""
    validated = MetadataFile.model_validate(metadata)
    payload = validated.model_dump(mode="json", exclude_none=False)
    for key, value in metadata.items():
        if key not in payload:
            payload[key] = value
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(payload, fh, sort_keys=False, allow_unicode=True)


def read_metadata(path: Path) -> dict[str, Any]:
    """Load metadata.yaml as a dict."""
    with path.open("r", encoding="utf-8") as fh:
        loaded = yaml.safe_load(fh)
    if loaded is None:
        return {}
    if not isinstance(loaded, dict):
        raise ValueError(f"metadata.yaml must be a mapping at {path}")
    return loaded


__all__ = ["MetadataFile", "read_metadata", "write_metadata"]
