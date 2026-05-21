from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import Difficulty, Layer, Task, TaskConfig
from ab_harness.scorers import SCORER_REGISTRY
from ab_harness.scorers.context_efficiency import context_efficiency_scorer


def _task() -> Task:
    return Task(
        id="L0_001",
        layer=Layer.L0,
        suite="file-ops",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
    )


def _write_traj(traj: Path, turns: list[dict]) -> None:
    events: list[dict] = [{"event": "run_start", "run_id": "r", "task_id": "L0_001"}]
    for i, t in enumerate(turns):
        events.append({
            "event": "turn",
            "idx": i,
            "role": t.get("role", "assistant"),
            "tool_calls": t.get("tool_calls", []),
            "tool_returns": t.get("tool_returns", []),
            "model_output": "",
            "vault_state_diff": None,
            "tokens_in": t.get("tokens_in", 0),
            "tokens_out": t.get("tokens_out", 0),
            "latency_ms": t.get("latency_ms", 0),
            "cost_usd": t.get("cost_usd", 0.0),
        })
    events.append({"event": "run_end", "status": "completed"})
    traj.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def test_registered() -> None:
    assert "context_efficiency" in SCORER_REGISTRY


def test_pass_under_target(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tokens_in": 50, "tokens_out": 50},
        {"tokens_in": 100, "tokens_out": 100},
    ])
    v = context_efficiency_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.pass_ is True
    assert v.score == 1.0
    assert isinstance(v.detail, dict)
    assert v.detail["total_tokens"] == 300
    assert v.detail["total_assistant_turns"] == 2


def test_linear_decay_midpoint(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    # target=1000, max=10000, span=9000. total=5500 -> 1 - (4500/9000) = 0.5
    _write_traj(traj, [{"tokens_in": 5500, "tokens_out": 0}])
    v = context_efficiency_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.score == pytest.approx(0.5)
    assert v.pass_ is True  # 0.5 >= 0.5


def test_fail_over_max(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [{"tokens_in": 20000, "tokens_out": 0}])
    v = context_efficiency_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.score == 0.0
    assert v.pass_ is False


def test_empty_trajectory(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [])
    v = context_efficiency_scorer(trajectory_path=traj, task=_task(), mode="run")
    # zero tokens -> below target -> score 1.0
    assert v.score == 1.0
    assert v.pass_ is True
    assert isinstance(v.detail, dict)
    assert v.detail["total_tokens"] == 0
    assert v.detail["total_assistant_turns"] == 0
    assert v.detail["avg_tokens_per_turn"] == 0.0


def test_run_and_replay_identical(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tokens_in": 4000, "tokens_out": 1500},
    ])
    v_run = context_efficiency_scorer(trajectory_path=traj, task=_task(), mode="run")
    v_replay = context_efficiency_scorer(trajectory_path=traj, task=_task(), mode="replay")
    assert v_run.score == v_replay.score
    assert v_run.pass_ == v_replay.pass_
    assert v_run.detail == v_replay.detail


def test_replay_unsupported_when_no_trajectory() -> None:
    v = context_efficiency_scorer(trajectory_path=None, task=_task(), mode="replay")
    assert v.pass_ is False
    assert isinstance(v.detail, dict)
    assert v.detail.get("replay_unsupported") is True


def test_custom_thresholds(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [{"tokens_in": 2000, "tokens_out": 0}])
    # custom target=5000 makes 2000 a pass at 1.0
    v = context_efficiency_scorer(
        trajectory_path=traj, task=_task(), mode="run",
        target_tokens=5000, max_tokens=50000,
    )
    assert v.score == 1.0
    assert v.pass_ is True


def test_only_assistant_turns_counted_in_avg(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"role": "assistant", "tokens_in": 100, "tokens_out": 100},
        {"role": "tool", "tokens_in": 0, "tokens_out": 0},
        {"role": "assistant", "tokens_in": 100, "tokens_out": 100},
    ])
    v = context_efficiency_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert isinstance(v.detail, dict)
    assert v.detail["total_assistant_turns"] == 2
    assert v.detail["total_tokens"] == 400
    assert v.detail["avg_tokens_per_turn"] == pytest.approx(200.0)
