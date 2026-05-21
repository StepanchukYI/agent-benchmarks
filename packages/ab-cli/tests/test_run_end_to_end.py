"""`ab run` end-to-end smoke against MockRunner — no live model calls."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from ab_cli.main import app
from ab_sdk.results import validate as validate_run_dir
from typer.testing import CliRunner

runner = CliRunner()


def _list_run_dirs(root: Path) -> list[Path]:
    return sorted([p for p in root.iterdir() if p.is_dir()])


@pytest.fixture
def results_dir(tmp_path: Path) -> Path:
    return tmp_path / "results"


def test_ab_run_single_task_mock(results_dir: Path) -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "L0_smoke",
            "--task",
            "L0_001",
            "--runner",
            "mock",
            "--model",
            "mock-model",
            "--tier",
            "T0",
            "--results-root",
            str(results_dir),
        ],
    )
    assert result.exit_code in {0, 1}, result.output

    run_dirs = _list_run_dirs(results_dir)
    assert len(run_dirs) == 1, f"expected exactly one run dir, got {run_dirs}"

    rd = run_dirs[0]
    for fname in ("trajectory.jsonl", "scores.json", "metadata.yaml", "workdir"):
        assert (rd / fname).exists(), f"missing {fname} in {rd}"

    issues = validate_run_dir(rd)
    assert issues == [], f"validate(rd) reported issues: {issues}"

    with (rd / "scores.json").open() as fh:
        scores = json.load(fh)
    assert scores["task_id"] == "L0_001"
    assert scores["tier"] == "T0"
    assert isinstance(scores["verdicts"], list) and len(scores["verdicts"]) >= 1

    with (rd / "metadata.yaml").open() as fh:
        meta = yaml.safe_load(fh)
    for key in ("run_id", "task_id", "model", "tier", "tier_hash", "harness", "status"):
        assert key in meta, f"metadata missing {key}"
    assert meta["status"] == "completed"


def test_ab_run_full_l0_smoke_mock(results_dir: Path) -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "L0_smoke",
            "--runner",
            "mock",
            "--model",
            "mock-model",
            "--tier",
            "T0",
            "--results-root",
            str(results_dir),
        ],
    )
    assert result.exit_code in {0, 1}, result.output

    run_dirs = _list_run_dirs(results_dir)
    assert len(run_dirs) == 5, f"expected 5 run dirs for L0 smoke; got {len(run_dirs)}"

    seen_task_ids: set[str] = set()
    for rd in run_dirs:
        issues = validate_run_dir(rd)
        assert issues == [], f"{rd}: {issues}"
        with (rd / "scores.json").open() as fh:
            seen_task_ids.add(json.load(fh)["task_id"])
    assert seen_task_ids == {"L0_001", "L0_002", "L0_003", "L0_004", "L0_005"}


def test_ab_run_unknown_task_exits_nonzero(results_dir: Path) -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "--suite",
            "L0_smoke",
            "--task",
            "L0_999",
            "--runner",
            "mock",
            "--results-root",
            str(results_dir),
        ],
    )
    assert result.exit_code != 0
