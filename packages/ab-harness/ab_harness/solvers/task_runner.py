"""Task orchestration: tier materialization -> runner.run_task -> scorer chain."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def run_single_task(
    task: Any,
    runner: Any,
    tier_manifest: Any,
    results_dir: str | Path,
) -> Path:
    raise NotImplementedError
