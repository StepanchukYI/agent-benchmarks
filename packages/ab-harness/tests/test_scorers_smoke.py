"""Smoke-test every scorer stub: each returns a ScorerVerdict with pass_=True."""

from __future__ import annotations

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_harness.scorers import (
    exec_scorer,
    file_diff_scorer,
    llm_judge_scorer,
    privacy_check_scorer,
    schema_validator_scorer,
    state_diff_scorer,
)


@pytest.mark.parametrize(
    "scorer",
    [
        file_diff_scorer,
        schema_validator_scorer,
        exec_scorer,
        llm_judge_scorer,
        state_diff_scorer,
        privacy_check_scorer,
    ],
)
def test_scorer_stub_passes(scorer):
    verdict = scorer()
    assert verdict.pass_ is True
