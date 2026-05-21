"""write_run_dir with scorer_verdicts produces a valid scores.json round-trip."""

from __future__ import annotations

from datetime import UTC, datetime

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Tier, Totals, Trajectory
from ab_sdk import read_scores, write_run_dir


def _trajectory() -> Trajectory:
    now = datetime.now(UTC)
    return Trajectory(
        run_id="run-002",
        task_id="L0_002",
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


def test_write_run_dir_with_scorer_verdicts(tmp_path):
    verdicts = [
        ScorerVerdict.model_validate(
            {
                "scorer_name": "schema_validator",
                "kind": ScorerKind.deterministic,
                "pass": True,
                "score": 1.0,
                "detail": "all fields present",
            }
        ),
        ScorerVerdict.model_validate(
            {
                "scorer_name": "privacy_check",
                "kind": ScorerKind.privacy_check,
                "pass": True,
                "score": 1.0,
                "detail": "no privacy pattern matches",
            }
        ),
    ]

    write_run_dir(
        tmp_path,
        _trajectory(),
        {"model": "claude", "tier": "T0", "dataset_version": "0.0.1"},
        scorer_verdicts=verdicts,
    )

    scores = read_scores(tmp_path)
    assert scores.run_id == "run-002"
    assert scores.task_id == "L0_002"
    assert scores.tier == "T0"
    assert scores.dataset_version == "ab-datasets==0.0.1"
    assert len(scores.verdicts) == 2
    assert scores.total_score == 1.0
    assert scores.pass_ is True


def test_total_score_is_mean_and_pass_requires_all(tmp_path):
    verdicts = [
        ScorerVerdict.model_validate(
            {
                "scorer_name": "a",
                "kind": ScorerKind.deterministic,
                "pass": True,
                "score": 1.0,
                "detail": "",
            }
        ),
        ScorerVerdict.model_validate(
            {
                "scorer_name": "b",
                "kind": ScorerKind.deterministic,
                "pass": False,
                "score": 0.0,
                "detail": "",
            }
        ),
    ]

    write_run_dir(
        tmp_path,
        _trajectory(),
        {"model": "claude", "tier": "T0", "dataset_version": "0.0.1"},
        scorer_verdicts=verdicts,
    )

    scores = read_scores(tmp_path)
    assert scores.total_score == 0.5
    assert scores.pass_ is False
