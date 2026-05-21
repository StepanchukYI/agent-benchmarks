from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import Difficulty, Layer, Task, TaskConfig
from ab_harness.scorers.deterministic import exec_scorer


def _task() -> Task:
    return Task(
        id="L0_004",
        layer=Layer.L0,
        suite="exec",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
    )


def test_exec_pass(tmp_path: Path) -> None:
    verdict = exec_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        cmd=[sys.executable, "-c", "print('hi')"],
        timeout=10,
        expected_exit=0,
    )
    assert verdict.pass_ is True
    assert verdict.score == 1.0
    assert isinstance(verdict.detail, dict)
    assert verdict.detail["exit_code"] == 0


def test_exec_fail_nonzero(tmp_path: Path) -> None:
    verdict = exec_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        cmd=[sys.executable, "-c", "import sys; sys.exit(3)"],
        timeout=10,
        expected_exit=0,
    )
    assert verdict.pass_ is False
    assert verdict.score == 0.0
    assert isinstance(verdict.detail, dict)
    assert verdict.detail["exit_code"] == 3


def test_exec_expected_exit_match(tmp_path: Path) -> None:
    verdict = exec_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        cmd=[sys.executable, "-c", "import sys; sys.exit(2)"],
        timeout=10,
        expected_exit=2,
    )
    assert verdict.pass_ is True


def test_exec_workdir_on_pythonpath(tmp_path: Path) -> None:
    (tmp_path / "foo.py").write_text("def add(x, y):\n    return x + y\n", encoding="utf-8")
    (tmp_path / "test_foo.py").write_text(
        "from foo import add\n\n\ndef test_a():\n    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    verdict = exec_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        cmd=[sys.executable, "-m", "pytest", "-q", "test_foo.py"],
        timeout=30,
        expected_exit=0,
    )
    assert verdict.pass_ is True, verdict.detail
    assert verdict.score == 1.0


def test_exec_replay_unsupported_without_trajectory(tmp_path: Path) -> None:
    verdict = exec_scorer(
        workdir=None,
        task=_task(),
        mode="replay",
        cmd=[sys.executable, "-c", "print('hi')"],
    )
    assert verdict.pass_ is False
    assert isinstance(verdict.detail, dict)
    assert verdict.detail.get("replay_unsupported") is True
