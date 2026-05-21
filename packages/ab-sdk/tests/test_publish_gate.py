"""Publish gate: validate + high-severity privacy scan."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Tier, Totals, Trajectory
from ab_sdk import check_publish_ready, write_run_dir

REPO_ROOT = Path(__file__).resolve().parents[3]
PATTERNS_PATH = REPO_ROOT / "docs" / "privacy-patterns.yaml"


def _trajectory(run_id: str = "run-pg") -> Trajectory:
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


def _write_clean(tmp_path: Path) -> Path:
    write_run_dir(
        tmp_path,
        _trajectory(),
        {"model": "claude", "tier": "T0", "dataset_version": "0.0.1"},
        scorer_verdicts=[_privacy_pass_verdict()],
    )
    return tmp_path


def test_clean_run_dir_passes(tmp_path):
    run_dir = _write_clean(tmp_path)
    ok, issues = check_publish_ready(run_dir, patterns_path=PATTERNS_PATH)
    assert ok, issues
    assert issues == []


def test_high_severity_pattern_blocks_publish(tmp_path):
    run_dir = _write_clean(tmp_path)

    trajectory_path = run_dir / "trajectory.jsonl"
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

    ok, issues = check_publish_ready(run_dir, patterns_path=PATTERNS_PATH)
    assert not ok
    assert any("github-token" in issue for issue in issues), issues


def test_missing_privacy_check_blocks_publish(tmp_path):
    write_run_dir(
        tmp_path,
        _trajectory("run-no-priv"),
        {"model": "claude", "tier": "T0", "dataset_version": "0.0.1"},
        scorer_verdicts=[
            ScorerVerdict.model_validate(
                {
                    "scorer_name": "schema_validator",
                    "kind": ScorerKind.deterministic,
                    "pass": True,
                    "score": 1.0,
                    "detail": "ok",
                }
            )
        ],
    )

    ok, issues = check_publish_ready(tmp_path, patterns_path=PATTERNS_PATH)
    assert not ok
    assert any("privacy gate" in issue for issue in issues), issues
