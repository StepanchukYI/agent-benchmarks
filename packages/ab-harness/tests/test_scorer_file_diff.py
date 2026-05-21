from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import Difficulty, Layer, Task, TaskConfig
from ab_harness.scorers.deterministic import file_diff_scorer


def _make_task() -> Task:
    return Task(
        id="L0_001",
        layer=Layer.L0,
        suite="file-ops",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
    )


def test_file_diff_pass_string_content(tmp_path: Path) -> None:
    (tmp_path / "hello.txt").write_text("hello\n", encoding="utf-8")
    verdict = file_diff_scorer(
        workdir=tmp_path,
        task=_make_task(),
        mode="run",
        expected={"hello.txt": "hello\n"},
    )
    assert verdict.pass_ is True
    assert verdict.score == 1.0


def test_file_diff_pass_sha256(tmp_path: Path) -> None:
    (tmp_path / "x.bin").write_bytes(b"abc")
    import hashlib

    sha = hashlib.sha256(b"abc").hexdigest()
    verdict = file_diff_scorer(
        workdir=tmp_path,
        task=_make_task(),
        mode="run",
        expected={"x.bin": {"sha256": sha}},
    )
    assert verdict.pass_ is True
    assert verdict.score == 1.0


def test_file_diff_must_be_absent(tmp_path: Path) -> None:
    (tmp_path / "new.txt").write_text("new", encoding="utf-8")
    verdict = file_diff_scorer(
        workdir=tmp_path,
        task=_make_task(),
        mode="run",
        expected={"new.txt": "new"},
        must_be_absent=["old.txt"],
    )
    assert verdict.pass_ is True
    assert verdict.score == 1.0


def test_file_diff_fail_content_mismatch(tmp_path: Path) -> None:
    (tmp_path / "f.txt").write_text("actual", encoding="utf-8")
    verdict = file_diff_scorer(
        workdir=tmp_path,
        task=_make_task(),
        mode="run",
        expected={"f.txt": "expected"},
    )
    assert verdict.pass_ is False
    assert verdict.score < 1.0
    assert isinstance(verdict.detail, dict)
    assert verdict.detail["differing"]


def test_file_diff_fail_must_be_absent(tmp_path: Path) -> None:
    (tmp_path / "still_here.txt").write_text("oops", encoding="utf-8")
    verdict = file_diff_scorer(
        workdir=tmp_path,
        task=_make_task(),
        mode="run",
        expected={},
        must_be_absent=["still_here.txt"],
    )
    assert verdict.pass_ is False


def test_file_diff_replay(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    events = [
        {"event": "run_start", "run_id": "r", "task_id": "L0_001"},
        {
            "event": "turn",
            "idx": 0,
            "role": "assistant",
            "tool_calls": [],
            "tool_returns": [{"path": "out/hi.txt", "content": "hello\n"}],
            "model_output": "",
            "vault_state_diff": {"created": ["out/hi.txt"], "modified": [], "deleted": []},
        },
        {"event": "run_end", "status": "completed"},
    ]
    traj.write_text("\n".join(json.dumps(e) for e in events) + "\n", encoding="utf-8")
    verdict = file_diff_scorer(
        trajectory_path=traj,
        task=_make_task(),
        mode="replay",
        expected={"out/hi.txt": "hello\n"},
        must_be_absent=["never.txt"],
    )
    assert verdict.pass_ is True
    assert verdict.score == 1.0
    assert isinstance(verdict.detail, dict)
    assert verdict.detail.get("mode") == "replay"
