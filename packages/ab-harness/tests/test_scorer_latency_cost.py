from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import Difficulty, Layer, Task, TaskConfig
from ab_harness.scorers import SCORER_REGISTRY
from ab_harness.scorers.latency_cost import latency_cost_scorer


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
    assert "latency_cost" in SCORER_REGISTRY


def test_pass_under_target_latency_zero_cost(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"latency_ms": 3000, "cost_usd": 0.0},
        {"latency_ms": 4000, "cost_usd": 0.0},
    ])
    v = latency_cost_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.pass_ is True
    assert v.score == 1.0
    assert isinstance(v.detail, dict)
    assert v.detail["total_latency_ms"] == 7000
    assert v.detail["total_cost_usd"] == 0.0
    assert v.detail["cost_score"] is None


def test_linear_decay_latency(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    # target=10000, max=120000, span=110000. value=65000 -> 1-(55000/110000)=0.5
    _write_traj(traj, [{"latency_ms": 65000}])
    v = latency_cost_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.score == pytest.approx(0.5)
    assert v.pass_ is True


def test_fail_over_max_latency(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [{"latency_ms": 200000}])
    v = latency_cost_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.score == 0.0
    assert v.pass_ is False


def test_cost_applied_when_max_cost_configured(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [{"latency_ms": 1000, "cost_usd": 0.5}])
    # latency under target -> 1.0; cost target=0, max=1.0 -> value=0.5 -> 0.5
    # final = min(1.0, 0.5) = 0.5
    v = latency_cost_scorer(
        trajectory_path=traj, task=_task(), mode="run",
        max_cost_usd=1.0,
    )
    assert v.score == pytest.approx(0.5)
    assert v.pass_ is True
    assert isinstance(v.detail, dict)
    assert v.detail["cost_score"] == pytest.approx(0.5)


def test_cost_ignored_when_max_cost_unset(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [{"latency_ms": 1000, "cost_usd": 99.0}])
    v = latency_cost_scorer(trajectory_path=traj, task=_task(), mode="run")
    # latency dominates; cost is 99 but ignored
    assert v.score == 1.0
    assert v.pass_ is True
    assert isinstance(v.detail, dict)
    assert v.detail["cost_score"] is None


def test_cost_with_custom_target(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [{"latency_ms": 0, "cost_usd": 0.05}])
    v = latency_cost_scorer(
        trajectory_path=traj, task=_task(), mode="run",
        max_cost_usd=1.0, target_cost_usd=0.1,
    )
    # cost 0.05 <= target 0.1 -> 1.0
    assert v.score == 1.0
    assert v.pass_ is True


def test_empty_trajectory(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [])
    v = latency_cost_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.score == 1.0
    assert v.pass_ is True
    assert isinstance(v.detail, dict)
    assert v.detail["total_latency_ms"] == 0
    assert v.detail["total_cost_usd"] == 0.0


def test_run_and_replay_identical(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"latency_ms": 30000, "cost_usd": 0.1},
        {"latency_ms": 15000, "cost_usd": 0.2},
    ])
    v_run = latency_cost_scorer(
        trajectory_path=traj, task=_task(), mode="run", max_cost_usd=1.0,
    )
    v_replay = latency_cost_scorer(
        trajectory_path=traj, task=_task(), mode="replay", max_cost_usd=1.0,
    )
    assert v_run.score == v_replay.score
    assert v_run.pass_ == v_replay.pass_
    assert v_run.detail == v_replay.detail


def test_replay_unsupported_when_no_trajectory() -> None:
    v = latency_cost_scorer(trajectory_path=None, task=_task(), mode="replay")
    assert v.pass_ is False
    assert isinstance(v.detail, dict)
    assert v.detail.get("replay_unsupported") is True
