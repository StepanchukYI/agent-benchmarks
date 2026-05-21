"""Iterate trajectory JSONL events and reassemble a Trajectory model."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


class TrajectoryReader:
    """Read events from a trajectory JSONL file."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def __iter__(self) -> Iterator[dict[str, Any]]:
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)

    @classmethod
    def to_trajectory(cls, path: str | Path) -> Any:
        from ab_datasets.schemas import Trajectory  # type: ignore[attr-defined]

        reader = cls(path)
        run_start: dict[str, Any] | None = None
        run_end: dict[str, Any] | None = None
        turns: list[dict[str, Any]] = []
        scorers: list[dict[str, Any]] = []

        for ev in reader:
            kind = ev.get("event")
            if kind == "run_start":
                run_start = ev
            elif kind == "turn":
                turns.append(ev)
            elif kind == "scorer":
                scorers.append(ev)
            elif kind == "run_end":
                run_end = ev

        if run_start is None:
            raise ValueError(f"trajectory missing run_start: {path}")
        if run_end is None:
            raise ValueError(f"trajectory missing run_end: {path}")

        payload: dict[str, Any] = {
            "run_id": run_start.get("run_id"),
            "task_id": run_start.get("task_id"),
            "model": run_start.get("model"),
            "harness": run_start.get("harness"),
            "tier": run_start.get("tier"),
            "tier_hash": run_start.get("tier_hash"),
            "dataset_version": run_start.get("dataset_version"),
            "prompt_template_hash": run_start.get("prompt_template_hash"),
            "started_at": run_start.get("started_at"),
            "finished_at": run_end.get("finished_at"),
            "status": run_end.get("status"),
            "turns": [{k: v for k, v in t.items() if k != "event"} for t in turns],
            "scorer_verdicts": [{k: v for k, v in s.items() if k != "event"} for s in scorers],
            "totals": run_end.get("totals"),
        }
        return Trajectory.model_validate(payload)
