from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ParsedRun:
    path: Path
    metadata: dict[str, Any]
    scores: dict[str, Any]
    run_id: str
    task_id: str
    model: str
    tier: str
    dataset_version: str
    source_commit_sha: str
    source_path: str


def iter_parsed_runs(
    clone_dir: Path,
    source_commit_sha: str,
) -> Iterator[ParsedRun]:
    clone_dir = Path(clone_dir)
    results_root = clone_dir / "results"
    if not results_root.exists() or not results_root.is_dir():
        return

    for entry in sorted(results_root.iterdir()):
        if not entry.is_dir():
            continue
        parsed = _parse_one(entry, clone_dir, source_commit_sha)
        if parsed is not None:
            yield parsed


def _parse_one(
    run_dir: Path,
    clone_dir: Path,
    source_commit_sha: str,
) -> ParsedRun | None:
    meta_path = run_dir / "metadata.yaml"
    scores_path = run_dir / "scores.json"
    traj_path = run_dir / "trajectory.jsonl"
    if not (meta_path.exists() and scores_path.exists() and traj_path.exists()):
        return None

    metadata = yaml.safe_load(meta_path.read_text(encoding="utf-8")) or {}
    if not isinstance(metadata, dict):
        return None
    with scores_path.open("r", encoding="utf-8") as fh:
        scores = json.load(fh)
    if not isinstance(scores, dict):
        return None

    run_id = str(metadata.get("run_id") or scores.get("run_id") or run_dir.name)
    task_id = str(metadata.get("task_id") or scores.get("task_id") or "")
    model = str(metadata.get("model") or scores.get("model") or "")
    tier = str(metadata.get("tier") or scores.get("tier") or "T0")
    dataset_version = str(
        metadata.get("dataset_version") or scores.get("dataset_version") or "unknown"
    )
    if not task_id or not model:
        return None

    source_path = str(run_dir.relative_to(clone_dir))

    return ParsedRun(
        path=run_dir,
        metadata=metadata,
        scores=scores,
        run_id=run_id,
        task_id=task_id,
        model=model,
        tier=tier,
        dataset_version=dataset_version,
        source_commit_sha=source_commit_sha,
        source_path=source_path,
    )
