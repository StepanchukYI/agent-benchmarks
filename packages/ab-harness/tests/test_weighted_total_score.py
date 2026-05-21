"""Weighted total_score aggregation across pillars.

Exercises ab_sdk.results.build_scores_payload with task.weights present,
missing pillars (penalty), and the empty-weights backward-compat path.
The pillar map under test lives in ab_harness.scorers.SCORER_PILLAR_MAP;
build_scores_payload imports it lazily, so this test pins the contract
between the two packages.
"""

from __future__ import annotations

import pytest

pytest.importorskip("ab_datasets.schemas")
pytest.importorskip("ab_sdk.results")

from ab_datasets.schemas import (
    Difficulty,
    Layer,
    ScorerKind,
    ScorerVerdict,
    Task,
    TaskConfig,
)
from ab_sdk.results import build_scores_payload


def _task(weights: dict[str, float] | None = None) -> Task:
    return Task(
        id="L0_weighted",
        layer=Layer.L0,
        suite="weighted",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
        scorer_chain=[],
        weights=weights or {},
    )


def _verdict(name: str, kind: ScorerKind, score: float, ok: bool = True) -> ScorerVerdict:
    return ScorerVerdict.model_validate(
        {
            "scorer_name": name,
            "kind": kind,
            "pass": ok,
            "score": score,
            "detail": "",
        }
    )


def _common_kwargs() -> dict[str, str]:
    return {
        "run_id": "run-weighted",
        "task_id": "L0_weighted",
        "model": "claude",
        "tier": "T0",
        "dataset_version": "ab-datasets==0.0.1",
    }


def test_weighted_total_two_pillars() -> None:
    """weights={correctness: 0.8, tool_skill: 0.2}, two verdicts → 0.8*1.0 + 0.2*0.5 = 0.9."""
    task = _task(weights={"correctness": 0.8, "tool_skill": 0.2})
    verdicts = [
        _verdict("file_diff", ScorerKind.deterministic, 1.0, ok=True),
        _verdict("tool_skill", ScorerKind.deterministic, 0.5, ok=True),
    ]

    payload = build_scores_payload(verdicts=verdicts, task=task, **_common_kwargs())

    assert payload["total_score"] == pytest.approx(0.9)
    assert payload["per_pillar"] == {
        "correctness": pytest.approx(1.0),
        "tool_skill": pytest.approx(0.5),
    }
    # all_verdicts pass AND total_score >= 0.5 → pass=True.
    assert payload["pass"] is True


def test_missing_pillar_is_penalized() -> None:
    """Weights declare tool_skill but no tool_skill verdict → that pillar contributes 0."""
    task = _task(weights={"correctness": 0.5, "tool_skill": 0.5})
    verdicts = [
        _verdict("file_diff", ScorerKind.deterministic, 1.0, ok=True),
    ]

    payload = build_scores_payload(verdicts=verdicts, task=task, **_common_kwargs())

    # correctness=1.0 weight 0.5, tool_skill missing → 0 * 0.5 → total = 0.5.
    assert payload["total_score"] == pytest.approx(0.5)
    assert payload["per_pillar"] == {"correctness": pytest.approx(1.0)}
    # all verdicts pass and total_score == 0.5 → pass=True (boundary).
    assert payload["pass"] is True


def test_no_weights_falls_back_to_mean() -> None:
    """Task without weights → unweighted mean over verdict scores (backward compat)."""
    task = _task(weights={})
    verdicts = [
        _verdict("file_diff", ScorerKind.deterministic, 1.0, ok=True),
        _verdict("tool_skill", ScorerKind.deterministic, 0.5, ok=True),
    ]

    payload = build_scores_payload(verdicts=verdicts, task=task, **_common_kwargs())

    assert payload["total_score"] == pytest.approx(0.75)
    # per_pillar still populated so downstream UI has the breakdown.
    assert payload["per_pillar"] == {
        "correctness": pytest.approx(1.0),
        "tool_skill": pytest.approx(0.5),
    }
    assert payload["pass"] is True


def test_no_task_argument_is_legacy_mean() -> None:
    """task=None preserves prior behaviour for callers that haven't migrated."""
    verdicts = [
        _verdict("a", ScorerKind.deterministic, 1.0, ok=True),
        _verdict("b", ScorerKind.deterministic, 0.0, ok=False),
    ]

    payload = build_scores_payload(verdicts=verdicts, **_common_kwargs())

    assert payload["total_score"] == pytest.approx(0.5)
    # all_verdicts_pass=False → pass is False even though total >= 0.5.
    assert payload["pass"] is False


def test_per_pillar_means_multiple_verdicts_per_pillar() -> None:
    """Multiple verdicts in one pillar → mean within pillar before weighting."""
    task = _task(weights={"correctness": 1.0})
    verdicts = [
        _verdict("file_diff", ScorerKind.deterministic, 1.0, ok=True),
        _verdict("schema", ScorerKind.schema, 0.0, ok=False),
    ]

    payload = build_scores_payload(verdicts=verdicts, task=task, **_common_kwargs())

    # mean(1.0, 0.0) = 0.5; weight 1.0 → total 0.5.
    assert payload["total_score"] == pytest.approx(0.5)
    assert payload["per_pillar"] == {"correctness": pytest.approx(0.5)}
    # one verdict failed → pass=False even at the boundary.
    assert payload["pass"] is False


def test_unknown_scorer_name_defaults_to_correctness() -> None:
    """Verdicts from unregistered scorer names fall into the correctness pillar."""
    task = _task(weights={"correctness": 1.0})
    verdicts = [
        _verdict("some_future_scorer", ScorerKind.deterministic, 0.8, ok=True),
    ]

    payload = build_scores_payload(verdicts=verdicts, task=task, **_common_kwargs())

    assert payload["total_score"] == pytest.approx(0.8)
    assert payload["per_pillar"] == {"correctness": pytest.approx(0.8)}


def test_extra_pillar_in_weights_with_no_coverage_zero() -> None:
    """memory_specific declared in weights but never has a verdict → score 0."""
    task = _task(
        weights={
            "correctness": 0.5,
            "tool_skill": 0.25,
            "memory_specific": 0.25,
        }
    )
    verdicts = [
        _verdict("file_diff", ScorerKind.deterministic, 1.0, ok=True),
        _verdict("tool_skill", ScorerKind.deterministic, 1.0, ok=True),
    ]

    payload = build_scores_payload(verdicts=verdicts, task=task, **_common_kwargs())

    # 0.5*1.0 + 0.25*1.0 + 0.25*0.0 = 0.75.
    assert payload["total_score"] == pytest.approx(0.75)
    assert "memory_specific" not in payload["per_pillar"]
    assert payload["per_pillar"]["correctness"] == pytest.approx(1.0)
    assert payload["per_pillar"]["tool_skill"] == pytest.approx(1.0)
