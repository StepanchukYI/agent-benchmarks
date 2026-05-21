"""Read, write, and validate a results/<utc>-<id>/ run dir."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerVerdict, Trajectory
from pydantic import BaseModel, ConfigDict

from .manifest import read_metadata, write_metadata

TRAJECTORY_FILE = "trajectory.jsonl"
SCORES_FILE = "scores.json"
METADATA_FILE = "metadata.yaml"


class RunDir(BaseModel):
    """Minimal handle to an on-disk run dir."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    path: Path
    run_id: str
    task_id: str
    model: str
    tier: str


def _trajectory_to_events(trajectory: Trajectory) -> list[dict[str, Any]]:
    dumped = trajectory.model_dump(mode="json", by_alias=True)
    events: list[dict[str, Any]] = []

    run_start: dict[str, Any] = {
        "event": "run_start",
        "run_id": dumped["run_id"],
        "task_id": dumped["task_id"],
        "model": dumped["model"],
        "harness": dumped["harness"],
        "tier": dumped["tier"],
        "tier_hash": dumped.get("tier_hash"),
        "dataset_version": dumped["dataset_version"],
        "prompt_template_hash": dumped.get("prompt_template_hash"),
        "started_at": dumped["started_at"],
    }
    events.append(run_start)

    for turn in dumped.get("turns", []):
        ev = {"event": "turn", **turn}
        events.append(ev)

    for verdict in dumped.get("scorer_verdicts", []):
        ev = {"event": "scorer", **verdict}
        events.append(ev)

    run_end: dict[str, Any] = {
        "event": "run_end",
        "finished_at": dumped.get("finished_at"),
        "status": dumped.get("status"),
        "totals": dumped.get("totals"),
    }
    events.append(run_end)
    return events


def write_run_dir(
    run_dir: Path,
    trajectory: Trajectory,
    metadata: dict[str, Any],
) -> None:
    """Write trajectory.jsonl, scores.json, and metadata.yaml into run_dir."""
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    events = _trajectory_to_events(trajectory)
    with (run_dir / TRAJECTORY_FILE).open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False))
            fh.write("\n")

    scores_payload: dict[str, Any] = {
        "run_id": trajectory.run_id,
        "task_id": trajectory.task_id,
        "model": trajectory.model,
        "tier": trajectory.tier.value if hasattr(trajectory.tier, "value") else trajectory.tier,
        "status": trajectory.status.value
        if trajectory.status is not None and hasattr(trajectory.status, "value")
        else trajectory.status,
        "totals": trajectory.totals.model_dump(mode="json") if trajectory.totals else None,
        "scorer_verdicts": [
            v.model_dump(mode="json", by_alias=True) for v in trajectory.scorer_verdicts
        ],
    }
    with (run_dir / SCORES_FILE).open("w", encoding="utf-8") as fh:
        json.dump(scores_payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    enriched = dict(metadata)
    enriched.setdefault("run_id", trajectory.run_id)
    enriched.setdefault("task_id", trajectory.task_id)
    enriched.setdefault("model", trajectory.model)
    enriched.setdefault(
        "tier",
        trajectory.tier.value if hasattr(trajectory.tier, "value") else trajectory.tier,
    )
    enriched.setdefault("dataset_version", trajectory.dataset_version)
    write_metadata(run_dir / METADATA_FILE, enriched)


def read_run_dir(run_dir: Path) -> RunDir:
    """Parse metadata.yaml and return a RunDir handle."""
    run_dir = Path(run_dir)
    meta = read_metadata(run_dir / METADATA_FILE)
    try:
        return RunDir(
            path=run_dir,
            run_id=str(meta["run_id"]),
            task_id=str(meta["task_id"]),
            model=str(meta["model"]),
            tier=str(meta["tier"]),
        )
    except KeyError as exc:
        raise ValueError(f"metadata.yaml missing required field: {exc.args[0]}") from exc


def read_trajectory(run_dir: Path) -> Trajectory:
    """Read trajectory.jsonl and reconstruct a Trajectory model."""
    run_dir = Path(run_dir)
    path = run_dir / TRAJECTORY_FILE

    events: list[dict[str, Any]]
    try:
        from ab_harness.trajectory.reader import TrajectoryReader  # type: ignore[import-not-found]

        events = list(TrajectoryReader(path))
    except ImportError:
        events = _iter_events_manual(path)

    return _reconstruct_trajectory(path, events)


def _iter_events_manual(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def _reconstruct_trajectory(path: Path, events: list[dict[str, Any]]) -> Trajectory:
    run_start: dict[str, Any] | None = None
    run_end: dict[str, Any] | None = None
    turns: list[dict[str, Any]] = []
    scorers: list[dict[str, Any]] = []

    for ev in events:
        kind = ev.get("event")
        if kind == "run_start":
            run_start = ev
        elif kind == "turn":
            turns.append({k: v for k, v in ev.items() if k != "event"})
        elif kind == "scorer":
            scorers.append({k: v for k, v in ev.items() if k != "event"})
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
        "turns": turns,
        "scorer_verdicts": scorers,
        "totals": run_end.get("totals"),
    }
    return Trajectory.model_validate(payload)


def validate(run_dir: Path) -> list[str]:
    """Return a list of issues with the run dir; empty list means valid."""
    run_dir = Path(run_dir)
    issues: list[str] = []

    for fname in (TRAJECTORY_FILE, SCORES_FILE, METADATA_FILE):
        if not (run_dir / fname).exists():
            issues.append(f"missing file: {fname}")

    traj_path = run_dir / TRAJECTORY_FILE
    if traj_path.exists():
        run_start_count = 0
        run_end_count = 0
        last_turn_idx = -1
        with traj_path.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError as exc:
                    issues.append(f"trajectory.jsonl line {lineno}: invalid JSON ({exc.msg})")
                    continue
                kind = ev.get("event")
                if kind == "run_start":
                    run_start_count += 1
                elif kind == "run_end":
                    run_end_count += 1
                elif kind == "turn":
                    idx = ev.get("idx")
                    if not isinstance(idx, int) or idx != last_turn_idx + 1:
                        issues.append(
                            f"trajectory.jsonl line {lineno}: turn idx {idx!r} not monotonic"
                        )
                    if isinstance(idx, int):
                        last_turn_idx = idx
        if run_start_count != 1:
            issues.append(f"trajectory.jsonl must have exactly one run_start (got {run_start_count})")
        if run_end_count != 1:
            issues.append(f"trajectory.jsonl must have exactly one run_end (got {run_end_count})")

    scores_path = run_dir / SCORES_FILE
    if scores_path.exists():
        try:
            with scores_path.open("r", encoding="utf-8") as fh:
                json.load(fh)
        except json.JSONDecodeError as exc:
            issues.append(f"scores.json: invalid JSON ({exc.msg})")

    return issues


__all__ = [
    "METADATA_FILE",
    "SCORES_FILE",
    "TRAJECTORY_FILE",
    "RunDir",
    "ScorerVerdict",
    "read_run_dir",
    "read_trajectory",
    "validate",
    "write_run_dir",
]
