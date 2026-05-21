"""Replay helper — re-run a recorded trajectory through a fresh runner."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ab_datasets.schemas import Trajectory


def replay(run_dir: Path, fresh_runner: Any) -> Trajectory:
    """Re-execute a recorded trajectory against fresh_runner; stub."""
    raise NotImplementedError(
        "replay is a Phase 1 deliverable (build spec §5 row 6); pending TrajectoryReader integration"
    )
