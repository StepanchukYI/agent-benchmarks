"""Docker sandbox: materialize a tier + task fixture (build spec §7)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def materialize(tier: Any, task: Any, workdir: str | Path) -> str:
    """Stub materializer that returns a deterministic tier_hash.

    Real implementation will pull a base image, install skills, mount CLAUDE.md,
    untar the vault snapshot, then return the rollup hash of the materialized
    bundle. For now we derive a hash from manifest.total_sha256 (if present)
    else from the tier name + task.id so tests are deterministic.
    """
    Path(workdir).mkdir(parents=True, exist_ok=True)

    total = getattr(tier, "total_sha256", None)
    if total:
        seed = str(total)
    else:
        tier_name = getattr(tier, "tier", None) or getattr(tier, "name", None) or str(tier)
        task_id = getattr(task, "id", None) or str(task)
        seed = f"{tier_name}:{task_id}"

    return hashlib.sha256(seed.encode("utf-8")).hexdigest()
