from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import Difficulty, Layer, Task, TaskConfig
from ab_harness.scorers import SCORER_REGISTRY
from ab_harness.scorers.tool_skill import tool_skill_scorer


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
    assert "tool_skill" in SCORER_REGISTRY


def test_pass_with_clean_signal(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tool_calls": [{"id": "1", "name": "Bash", "args": {"command": "ls"}}]},
        {"role": "tool", "tool_returns": [{"tool_use_id": "1", "is_error": False}]},
        {"tool_calls": [{"id": "2", "name": "Write", "args": {"file_path": "f", "content": "x"}}]},
        {"role": "tool", "tool_returns": [{"tool_use_id": "2", "is_error": False}]},
    ])
    v = tool_skill_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.pass_ is True
    assert v.score == 1.0
    assert isinstance(v.detail, dict)
    assert v.detail["total_calls"] == 2
    assert v.detail["error_calls"] == 0


def test_fail_with_high_error_rate(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tool_calls": [{"id": "1", "name": "Bash", "args": {"command": "bad1"}}]},
        {"role": "tool", "tool_returns": [{"tool_use_id": "1", "is_error": True}]},
        {"tool_calls": [{"id": "2", "name": "Bash", "args": {"command": "bad2"}}]},
        {"role": "tool", "tool_returns": [{"tool_use_id": "2", "is_error": True}]},
        {"tool_calls": [{"id": "3", "name": "Bash", "args": {"command": "ok"}}]},
        {"role": "tool", "tool_returns": [{"tool_use_id": "3", "is_error": False}]},
    ])
    # error_rate = 2/3 > 0.25 -> -0.5 -> 0.5 -> below 0.7 -> fail
    v = tool_skill_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.pass_ is False
    assert v.score == pytest.approx(0.5)
    assert isinstance(v.detail, dict)
    assert v.detail["error_calls"] == 2


def test_redundant_calls_penalty(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    # 4 identical consecutive calls -> 3 redundant out of 4 = 0.75 > 0.5
    _write_traj(traj, [
        {"tool_calls": [{"id": f"i{i}", "name": "Bash", "args": {"command": "ls"}}]}
        for i in range(4)
    ])
    v = tool_skill_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert isinstance(v.detail, dict)
    assert v.detail["redundant_ratio"] >= 0.5
    # -0.3 from redundancy -> 0.7 -> exactly threshold = pass
    assert v.score == pytest.approx(0.7)
    assert v.pass_ is True


def test_too_many_calls_penalty(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    # 60 distinct calls -> over default max_tool_calls=50 -> -0.2
    _write_traj(traj, [
        {"tool_calls": [{"id": f"i{i}", "name": "Bash", "args": {"command": f"c{i}"}}]}
        for i in range(60)
    ])
    v = tool_skill_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert isinstance(v.detail, dict)
    assert v.detail["total_calls"] == 60
    assert v.score == pytest.approx(0.8)
    assert v.pass_ is True  # 0.8 >= 0.7


def test_combined_penalties_floor_at_zero(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    turns: list[dict] = []
    # 60 identical calls all erroring -> redundant>0.5, error>0.25, total>50
    for i in range(60):
        turns.append({"tool_calls": [{"id": f"i{i}", "name": "Bash", "args": {"command": "ls"}}]})
        turns.append({"role": "tool", "tool_returns": [{"tool_use_id": f"i{i}", "is_error": True}]})
    _write_traj(traj, turns)
    v = tool_skill_scorer(trajectory_path=traj, task=_task(), mode="run")
    # 1 - 0.5 - 0.3 - 0.2 = 0.0
    assert v.score == 0.0
    assert v.pass_ is False


def test_empty_trajectory(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [])
    v = tool_skill_scorer(trajectory_path=traj, task=_task(), mode="run")
    assert v.pass_ is True
    assert v.score == 1.0
    assert isinstance(v.detail, dict)
    assert v.detail["total_calls"] == 0


def test_replay_identical_to_run(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tool_calls": [{"id": "1", "name": "Bash", "args": {"command": "ls"}}]},
        {"role": "tool", "tool_returns": [{"tool_use_id": "1", "is_error": True}]},
        {"tool_calls": [{"id": "2", "name": "Bash", "args": {"command": "ls"}}]},
        {"role": "tool", "tool_returns": [{"tool_use_id": "2", "is_error": True}]},
    ])
    v_run = tool_skill_scorer(trajectory_path=traj, task=_task(), mode="run")
    v_replay = tool_skill_scorer(trajectory_path=traj, task=_task(), mode="replay")
    assert v_run.score == v_replay.score
    assert v_run.pass_ == v_replay.pass_
    assert v_run.detail == v_replay.detail


def test_replay_unsupported_when_no_trajectory(tmp_path: Path) -> None:
    v = tool_skill_scorer(trajectory_path=None, task=_task(), mode="replay")
    assert v.pass_ is False
    assert isinstance(v.detail, dict)
    assert v.detail.get("replay_unsupported") is True


def test_custom_thresholds_via_config(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tool_calls": [{"id": f"i{i}", "name": "Bash", "args": {"command": f"c{i}"}}]}
        for i in range(3)
    ])
    # max_tool_calls=2 -> over -> -0.2 -> 0.8 -> still >= pass_threshold 0.5
    v = tool_skill_scorer(
        trajectory_path=traj, task=_task(), mode="run",
        max_tool_calls=2, pass_threshold=0.5,
    )
    assert v.score == pytest.approx(0.8)
    assert v.pass_ is True
