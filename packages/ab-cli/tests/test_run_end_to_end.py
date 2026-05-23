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
    # The L0_smoke suite grows with the backlog (target 20 per build spec §2).
    # Require at least the original five smoke tasks but accept more.
    assert len(run_dirs) >= 5, (
        f"expected ≥5 run dirs for L0_smoke; got {len(run_dirs)}"
    )

    seen_task_ids: set[str] = set()
    for rd in run_dirs:
        issues = validate_run_dir(rd)
        assert issues == [], f"{rd}: {issues}"
        with (rd / "scores.json").open() as fh:
            seen_task_ids.add(json.load(fh)["task_id"])
    assert {"L0_001", "L0_002", "L0_003", "L0_004", "L0_005"}.issubset(seen_task_ids), (
        f"missing original five from seen_task_ids={sorted(seen_task_ids)}"
    )


def test_ab_run_claude_md_missing_file_exits_2(results_dir: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        [
            "run",
            "--suite", "L0_smoke",
            "--task", "L0_001",
            "--runner", "mock",
            "--tier", "T0",
            "--claude-md", str(tmp_path / "nope.md"),
            "--results-root", str(results_dir),
        ],
    )
    assert result.exit_code == 2, result.output


def test_ab_run_custom_prompt_distinct_hash_and_label(
    results_dir: Path, tmp_path: Path
) -> None:
    """--claude-md + --prompt-label: run_start carries label + verbatim text,
    and tier_hash differs from a vanilla T0 run."""
    custom = tmp_path / "karpathy.md"
    custom.write_text("# Karpathy rules\nBe terse.\n", encoding="utf-8")

    # Vanilla T0 baseline.
    base_root = results_dir / "base"
    r0 = runner.invoke(
        app,
        ["run", "--suite", "L0_smoke", "--task", "L0_001", "--runner", "mock",
         "--tier", "T0", "--results-root", str(base_root)],
    )
    assert r0.exit_code in {0, 1}, r0.output

    # Custom prompt run.
    cust_root = results_dir / "cust"
    r1 = runner.invoke(
        app,
        ["run", "--suite", "L0_smoke", "--task", "L0_001", "--runner", "mock",
         "--tier", "T0", "--claude-md", str(custom),
         "--prompt-label", "karpathy-rules", "--results-root", str(cust_root)],
    )
    assert r1.exit_code in {0, 1}, r1.output

    base_rs = _read_run_start(_list_run_dirs(base_root)[0])
    cust_rs = _read_run_start(_list_run_dirs(cust_root)[0])

    # Custom prompt is a distinct identity.
    assert cust_rs["tier_hash"] != base_rs["tier_hash"]
    assert cust_rs["prompt_label"] == "karpathy-rules"
    assert base_rs["prompt_label"] is None
    # Verbatim prompt is captured for the reveal + privacy scan.
    assert "# Karpathy rules" in cust_rs["system_prompt_verbatim"]
    # metadata.yaml carries the label too (the ingest reads run dir).
    with (_list_run_dirs(cust_root)[0] / "metadata.yaml").open() as fh:
        assert yaml.safe_load(fh)["prompt_label"] == "karpathy-rules"


def _read_run_start(run_dir: Path) -> dict:
    line = (run_dir / "trajectory.jsonl").read_text().splitlines()[0]
    return json.loads(line)


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
