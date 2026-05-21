"""build_scores_payload validates task.weights — negative/zero/mismatched sums."""

from __future__ import annotations

import logging

import pytest
from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task
from ab_sdk.results import build_scores_payload


def _verdicts() -> list[ScorerVerdict]:
    return [
        ScorerVerdict.model_validate(
            {
                "scorer_name": "schema_validator",
                "kind": ScorerKind.deterministic,
                "pass": True,
                "score": 1.0,
                "detail": "",
            }
        ),
        ScorerVerdict.model_validate(
            {
                "scorer_name": "tool_skill",
                "kind": ScorerKind.deterministic,
                "pass": True,
                "score": 0.5,
                "detail": "",
            }
        ),
    ]


def _task(weights: dict[str, float]) -> Task:
    return Task.model_validate(
        {
            "id": "L0_999",
            "layer": "L0",
            "suite": "weight-test",
            "title": "weight test",
            "description": "",
            "config": {"required_tier": "T0", "recommended_tier": "T0"},
            "weights": weights,
        }
    )


def _build(**overrides) -> dict:
    defaults = dict(
        run_id="r1",
        task_id="L0_999",
        model="claude-sonnet",
        tier="T0",
        dataset_version="ab-datasets==0.0.1",
        verdicts=_verdicts(),
    )
    defaults.update(overrides)
    return build_scores_payload(**defaults)


def test_negative_weight_raises_value_error() -> None:
    task = _task({"correctness": 0.5, "tool_skill": -0.5})
    with pytest.raises(ValueError, match="negative weight not allowed"):
        _build(task=task)


def test_zero_sum_weights_falls_back_to_unweighted_mean(
    caplog: pytest.LogCaptureFixture,
) -> None:
    task = _task({"correctness": 0.0, "tool_skill": 0.0})
    with caplog.at_level(logging.WARNING, logger="ab_sdk.results"):
        payload = _build(task=task)
    # Verdict mean: (1.0 + 0.5) / 2 = 0.75.
    assert payload["total_score"] == pytest.approx(0.75)
    assert any("sum to zero" in rec.message for rec in caplog.records)


def test_mismatched_sum_warns_but_proceeds(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # Sums to 1.5 — well outside [0.95, 1.05] but otherwise valid.
    task = _task({"correctness": 1.0, "tool_skill": 0.5})
    with caplog.at_level(logging.WARNING, logger="ab_sdk.results"):
        payload = _build(task=task)
    # 1.0 * 1.0 + 0.5 * 0.5 = 1.25 — proceeds with bad math, but warns.
    assert payload["total_score"] == pytest.approx(1.25)
    assert any("expected ~1.0" in rec.message for rec in caplog.records)


def test_valid_weights_no_warnings(caplog: pytest.LogCaptureFixture) -> None:
    task = _task({"correctness": 0.7, "tool_skill": 0.3})
    with caplog.at_level(logging.WARNING, logger="ab_sdk.results"):
        payload = _build(task=task)
    # 0.7 * 1.0 + 0.3 * 0.5 = 0.85.
    assert payload["total_score"] == pytest.approx(0.85)
    assert caplog.records == []
