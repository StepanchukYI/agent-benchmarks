"""Regression test for the write-path / read-path scoring mismatch.

`ab_sdk.results.build_scores_payload` computes total_score as a weighted
sum over pillars; the rescoring engine previously used an unweighted
mean over verdicts. Any task with non-uniform weights would therefore
produce diverging totals even when the agent's behavior was identical,
blocking the `verified` trust tier permanently.

This test asserts the two code paths produce the same number on the
same verdict set.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from ab_datasets.schemas import ScorerVerdict
from ab_sdk.results import compute_total_score


def _v(name: str, score: float, pass_: bool = True) -> ScorerVerdict:
    return ScorerVerdict(
        scorer_name=name,
        kind="deterministic",
        pass_=pass_,
        score=score,
        detail={},
    )


def test_compute_total_score_matches_weighted_sum() -> None:
    """Single source-of-truth: rescoring engine and build_scores_payload
    must use the SAME helper, and the helper must apply weights."""
    verdicts = [
        _v("file_diff", 1.0),
        _v("tool_skill", 0.5),
        _v("context_efficiency", 0.5),
        _v("latency_cost", 0.5),
    ]
    task = SimpleNamespace(
        weights={
            "correctness": 0.80,
            "tool_skill": 0.10,
            "context_efficiency": 0.05,
            "latency_cost": 0.05,
            "memory_specific": 0.00,
        }
    )

    total, per_pillar = compute_total_score(verdicts, task)
    # correctness=1.0 (file_diff alone), other 3 pillars=0.5 each.
    # total = 0.8*1.0 + 0.1*0.5 + 0.05*0.5 + 0.05*0.5 + 0.0*0
    #       = 0.8 + 0.05 + 0.025 + 0.025 = 0.9
    assert total == pytest.approx(0.9, abs=1e-9)
    assert per_pillar["correctness"] == pytest.approx(1.0)
    assert per_pillar["tool_skill"] == pytest.approx(0.5)


def test_compute_total_score_no_task_falls_back_to_mean() -> None:
    verdicts = [_v("file_diff", 1.0), _v("privacy_check", 0.0)]
    total, _ = compute_total_score(verdicts, task=None)
    assert total == pytest.approx(0.5)


def test_compute_total_score_zero_sum_weights_falls_back() -> None:
    verdicts = [_v("file_diff", 1.0), _v("privacy_check", 0.0)]
    task = SimpleNamespace(weights={"correctness": 0.0, "tool_skill": 0.0})
    total, _ = compute_total_score(verdicts, task)
    # Zero-sum → falls back to unweighted mean → 0.5
    assert total == pytest.approx(0.5)


def test_compute_total_score_rejects_negative_weight() -> None:
    verdicts = [_v("file_diff", 1.0)]
    task = SimpleNamespace(weights={"correctness": -0.1, "tool_skill": 1.1})
    with pytest.raises(ValueError, match="negative weight"):
        compute_total_score(verdicts, task)


def test_compute_total_score_missing_pillar_penalized() -> None:
    """Pillar declared in weights but no verdict → contributes 0."""
    verdicts = [_v("file_diff", 1.0)]
    task = SimpleNamespace(
        weights={"correctness": 0.5, "tool_skill": 0.5}
    )
    total, per_pillar = compute_total_score(verdicts, task)
    # correctness=1.0, tool_skill=missing → 0
    # total = 0.5*1.0 + 0.5*0.0 = 0.5
    assert total == pytest.approx(0.5)
    assert "tool_skill" not in per_pillar
