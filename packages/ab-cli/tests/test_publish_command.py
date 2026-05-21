"""`ab publish` CLI test: synthetic run dir, mocked git subprocess, privacy gate."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ab_cli.main import app
from ab_datasets.schemas import ScorerKind, ScorerVerdict, Tier, Totals, Trajectory
from ab_sdk.results import write_run_dir
from typer.testing import CliRunner

REPO_ROOT = Path(__file__).resolve().parents[3]
PATTERNS_PATH = REPO_ROOT / "docs" / "privacy-patterns.yaml"


def _trajectory(run_id: str = "run-pub") -> Trajectory:
    now = datetime.now(UTC)
    return Trajectory(
        run_id=run_id,
        task_id="L0_001",
        model="claude",
        harness="claude-code-cli@0.4.1",
        tier=Tier.T0,
        dataset_version="ab-datasets==0.0.1",
        started_at=now,
        finished_at=now,
        turns=[],
        status="completed",
        totals=Totals(tokens_in=0, tokens_out=0, latency_ms=0, cost_usd=0.0, score=0.0),
    )


def _privacy_pass_verdict() -> ScorerVerdict:
    return ScorerVerdict.model_validate(
        {
            "scorer_name": "privacy_check",
            "kind": ScorerKind.privacy_check,
            "pass": True,
            "score": 1.0,
            "detail": "no privacy pattern matches",
        }
    )


def _make_clean_run(results_dir: Path, name: str = "20260520T120000Z-run-abc") -> Path:
    rd = results_dir / name
    write_run_dir(
        rd,
        _trajectory(name),
        {"model": "claude", "tier": "T0", "dataset_version": "0.0.1"},
        scorer_verdicts=[_privacy_pass_verdict()],
    )
    return rd


@pytest.fixture
def isolated_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "xdg-config"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    monkeypatch.setenv("AB_PRIVACY_PATTERNS", str(PATTERNS_PATH))
    return tmp_path


def test_publish_dry_run_reports_summary(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results_dir = isolated_env / "results"
    results_dir.mkdir()
    _make_clean_run(results_dir)

    git_calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        git_calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("ab_cli.commands.publish.subprocess.run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "publish",
            "--dry-run",
            "--server",
            "http://localhost:8000",
            "--repo",
            "file:///tmp/results.git",
            "--results-dir",
            str(results_dir),
        ],
    )
    assert result.exit_code == 0, result.output
    assert "would publish 1 run dir" in result.output.lower()
    assert git_calls == []


def test_publish_blocks_on_privacy_failure(
    isolated_env: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    results_dir = isolated_env / "results"
    results_dir.mkdir()
    rd = _make_clean_run(results_dir, "20260520T120100Z-run-tainted")

    trajectory_path = rd / "trajectory.jsonl"
    lines = trajectory_path.read_text(encoding="utf-8").splitlines()
    tainted_turn = {
        "event": "turn",
        "idx": 0,
        "role": "assistant",
        "prompt_delta": None,
        "tool_calls": [],
        "tool_returns": [],
        "model_output": "leaked token ghp_" + "a" * 36,
        "vault_state_diff": None,
        "tokens_in": 0,
        "tokens_out": 0,
        "latency_ms": 0,
        "cost_usd": 0.0,
    }
    new_lines = [lines[0], json.dumps(tainted_turn), *lines[1:]]
    trajectory_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    git_calls: list[list[str]] = []

    def fake_run(args, **kwargs):
        git_calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("ab_cli.commands.publish.subprocess.run", fake_run)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "publish",
            "--server",
            "http://localhost:8000",
            "--repo",
            "file:///tmp/results.git",
            "--results-dir",
            str(results_dir),
        ],
    )
    assert result.exit_code != 0
    assert "privacy-gate failed" in result.output.lower()
    assert git_calls == []
