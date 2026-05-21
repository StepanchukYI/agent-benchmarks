from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import Difficulty, Layer, Task, TaskConfig
from ab_harness.scorers import SCORER_REGISTRY
from ab_harness.scorers.file_invariants import readme_exact_scorer


def _task() -> Task:
    return Task(
        id="L0_005",
        layer=Layer.L0,
        suite="extract",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
    )


_README = "- alpha\n- beta\n- gamma\n"


def test_registered() -> None:
    assert "readme_exact" in SCORER_REGISTRY


def test_pass_when_content_matches(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text(_README, encoding="utf-8")
    verdict = readme_exact_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        expected={"README.md": _README},
    )
    assert verdict.pass_ is True
    assert verdict.score == 1.0


def test_fail_when_content_differs(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("- alpha\n- beta\n", encoding="utf-8")
    verdict = readme_exact_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        expected={"README.md": _README},
    )
    assert verdict.pass_ is False
    assert verdict.score < 1.0
    assert isinstance(verdict.detail, dict)
    assert verdict.detail["differing"]


def test_fail_when_file_missing(tmp_path: Path) -> None:
    verdict = readme_exact_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        expected={"README.md": _README},
    )
    assert verdict.pass_ is False
    assert isinstance(verdict.detail, dict)
    assert verdict.detail["differing"][0]["reason"] == "missing"


def test_fail_when_includes_private_helper(tmp_path: Path) -> None:
    """L0_005 says `_private` must not appear; this is enforced by exact match."""
    (tmp_path / "README.md").write_text("- alpha\n- beta\n- gamma\n- _private\n", encoding="utf-8")
    verdict = readme_exact_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        expected={"README.md": _README},
    )
    assert verdict.pass_ is False


def _write_traj(traj: Path, turns: list[dict]) -> None:
    events = [{"event": "run_start", "run_id": "r", "task_id": "L0_005"}]
    for i, t in enumerate(turns):
        ev = {
            "event": "turn",
            "idx": i,
            "role": t.get("role", "assistant"),
            "tool_calls": t.get("tool_calls", []),
            "tool_returns": t.get("tool_returns", []),
            "model_output": "",
            "vault_state_diff": None,
        }
        events.append(ev)
    events.append({"event": "run_end", "status": "completed"})
    traj.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")


def test_replay_pass_from_write_tool_call(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tool_calls": [{"id": "1", "name": "Write", "args": {"file_path": "README.md", "content": _README}}]},
    ])
    verdict = readme_exact_scorer(
        trajectory_path=traj,
        task=_task(),
        mode="replay",
        expected={"README.md": _README},
    )
    assert verdict.pass_ is True
    assert isinstance(verdict.detail, dict)
    assert verdict.detail.get("mode") == "replay"


def test_replay_fail_when_content_mismatch(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tool_calls": [{"id": "1", "name": "Write", "args": {"file_path": "README.md", "content": "- alpha\n"}}]},
    ])
    verdict = readme_exact_scorer(
        trajectory_path=traj,
        task=_task(),
        mode="replay",
        expected={"README.md": _README},
    )
    assert verdict.pass_ is False
    assert isinstance(verdict.detail, dict)
    assert verdict.detail["differing"]


def test_replay_unsupported_when_no_writes(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [{"tool_calls": []}])
    verdict = readme_exact_scorer(
        trajectory_path=traj,
        task=_task(),
        mode="replay",
        expected={"README.md": _README},
    )
    assert verdict.pass_ is False
    assert isinstance(verdict.detail, dict)
    assert verdict.detail.get("replay_unsupported") is True


def test_replay_uses_last_write_when_multiple(tmp_path: Path) -> None:
    """Last write should win."""
    traj = tmp_path / "trajectory.jsonl"
    _write_traj(traj, [
        {"tool_calls": [{"id": "1", "name": "Write", "args": {"file_path": "README.md", "content": "- alpha\n"}}]},
        {"tool_calls": [{"id": "2", "name": "Write", "args": {"file_path": "README.md", "content": _README}}]},
    ])
    verdict = readme_exact_scorer(
        trajectory_path=traj,
        task=_task(),
        mode="replay",
        expected={"README.md": _README},
    )
    assert verdict.pass_ is True
