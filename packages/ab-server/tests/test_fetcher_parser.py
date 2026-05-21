from __future__ import annotations

import json
from pathlib import Path

from ab_server.fetcher.parser import iter_parsed_runs


def _write_run(run_dir: Path, run_id: str, task_id: str) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task_id}\nmodel: claude-sonnet\ntier: T0\ndataset_version: 0.0.1\nharness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    (run_dir / "scores.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "task_id": task_id,
                "total_score": 1.0,
                "pass": True,
            }
        )
        + "\n"
    )
    (run_dir / "trajectory.jsonl").write_text("{}\n")


def test_iter_parsed_runs_yields_one_per_dir(tmp_path: Path) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run(clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001")
    _write_run(clone / "results" / "20260521T000100Z-run-2", "run-2", "L0_002")

    runs = list(iter_parsed_runs(clone, source_commit_sha="abc123"))
    assert len(runs) == 2
    ids = {r.run_id for r in runs}
    assert ids == {"run-1", "run-2"}
    for run in runs:
        assert run.source_commit_sha == "abc123"
        assert run.source_path.startswith("results/")
        assert run.model == "claude-sonnet"
        assert run.tier == "T0"


def test_iter_parsed_runs_skips_incomplete(tmp_path: Path) -> None:
    clone = tmp_path / "clone"
    (clone / "results" / "20260521T000000Z-broken").mkdir(parents=True)
    (clone / "results" / "20260521T000000Z-broken" / "metadata.yaml").write_text(
        "run_id: broken\ntask_id: L0_001\nmodel: m\ntier: T0\ndataset_version: 0.0.1\n"
    )
    runs = list(iter_parsed_runs(clone, source_commit_sha="abc"))
    assert runs == []


def test_iter_parsed_runs_missing_results_dir(tmp_path: Path) -> None:
    runs = list(iter_parsed_runs(tmp_path / "nope", source_commit_sha="abc"))
    assert runs == []
