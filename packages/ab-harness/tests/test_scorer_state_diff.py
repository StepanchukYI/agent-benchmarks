from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import Difficulty, Layer, Task, TaskConfig
from ab_harness.scorers.state_diff import state_diff_scorer


def _task() -> Task:
    return Task(
        id="L0_x",
        layer=Layer.L0,
        suite="state",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
    )


def _write_trajectory(path: Path, turns: list[dict]) -> None:
    events = [{"event": "run_start", "run_id": "r", "task_id": "T"}]
    for i, t in enumerate(turns):
        events.append({"event": "turn", "idx": i, "role": "assistant", **t})
    events.append({"event": "run_end", "status": "completed"})
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def test_state_diff_pass(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_trajectory(
        traj,
        [
            {"vault_state_diff": {"created": ["a.md", "b.md"], "modified": [], "deleted": []}},
            {"vault_state_diff": {"created": [], "modified": ["c.md"], "deleted": []}},
        ],
    )
    verdict = state_diff_scorer(
        trajectory_path=traj,
        task=_task(),
        mode="run",
        expected_created=["a.md", "b.md"],
        expected_modified=["c.md"],
    )
    assert verdict.pass_ is True
    assert verdict.score == 1.0


def test_state_diff_fail_missing_path(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_trajectory(
        traj,
        [{"vault_state_diff": {"created": ["a.md"], "modified": [], "deleted": []}}],
    )
    verdict = state_diff_scorer(
        trajectory_path=traj,
        task=_task(),
        mode="run",
        expected_created=["a.md", "b.md"],
    )
    assert verdict.pass_ is False
    assert isinstance(verdict.detail, dict)
    assert "b.md" in verdict.detail["missing"]["created"]


def test_state_diff_jaccard_score(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_trajectory(
        traj,
        [
            {
                "vault_state_diff": {
                    "created": ["a.md", "extra.md"],
                    "modified": [],
                    "deleted": [],
                }
            }
        ],
    )
    verdict = state_diff_scorer(
        trajectory_path=traj,
        task=_task(),
        mode="run",
        expected_created=["a.md"],
    )
    assert verdict.pass_ is True  # all expected appear
    assert 0.0 < verdict.score < 1.0


def test_state_diff_deletions(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_trajectory(
        traj,
        [{"vault_state_diff": {"created": [], "modified": [], "deleted": ["old.md"]}}],
    )
    verdict = state_diff_scorer(
        trajectory_path=traj,
        task=_task(),
        mode="run",
        expected_deleted=["old.md"],
    )
    assert verdict.pass_ is True
