"""Smoke-test: scorer module imports cleanly and llm_judge stub passes.

Real-impl scorers (file_diff, exec, schema, state_diff, privacy_check) have
their own dedicated test_scorer_*.py files. This smoke test only guards
import-time wiring and the llm_judge stub contract.
"""

from __future__ import annotations

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_harness.scorers import (
    SCORER_REGISTRY,
    exec_scorer,
    file_diff_scorer,
    llm_judge_scorer,
    privacy_check_scorer,
    schema_scorer,
    state_diff_scorer,
)


def test_registry_has_all_scorers():
    for name in ["file_diff", "exec", "schema", "state_diff", "privacy_check", "llm_judge"]:
        assert name in SCORER_REGISTRY


def test_llm_judge_stub_passes():
    verdict = llm_judge_scorer()
    assert verdict.pass_ is True
    assert verdict.score == 1.0


def test_all_scorers_callable():
    for fn in (
        file_diff_scorer,
        exec_scorer,
        schema_scorer,
        state_diff_scorer,
        privacy_check_scorer,
        llm_judge_scorer,
    ):
        assert callable(fn)
