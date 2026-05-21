"""Scorer implementations: deterministic, schema, exec, llm-judge, state-diff, privacy-check.

The registry is keyed by (kind, name) AND (name) — the chain runner dispatches
on the `kind` first (from `ScorerSpec.kind`), then falls back to looking up by name.
"""

from __future__ import annotations

from collections.abc import Callable

from ab_datasets.schemas import ScorerKind

from ab_harness.scorers._base import Scorer, replay_unsupported, score_to_verdict
from ab_harness.scorers.deterministic import (
    exec_scorer,
    file_diff_scorer,
    schema_validator_scorer,
)
from ab_harness.scorers.file_invariants import (
    readme_exact_scorer,
    test_file_unchanged_scorer,
)
from ab_harness.scorers.llm_judge import llm_judge_scorer
from ab_harness.scorers.privacy_check import privacy_check_scorer
from ab_harness.scorers.schema import schema_scorer
from ab_harness.scorers.state_diff import state_diff_scorer

ScorerCallable = Callable[..., object]

SCORER_REGISTRY: dict[str, ScorerCallable] = {
    "file_diff": file_diff_scorer,
    "exec": exec_scorer,
    "schema": schema_scorer,
    "schema_validator": schema_scorer,
    "state_diff": state_diff_scorer,
    "privacy_check": privacy_check_scorer,
    "llm_judge": llm_judge_scorer,
    "test_file_unchanged": test_file_unchanged_scorer,
    "readme_exact": readme_exact_scorer,
}

KIND_DEFAULT_REGISTRY: dict[ScorerKind, ScorerCallable] = {
    ScorerKind.exec: exec_scorer,
    ScorerKind.schema: schema_scorer,
    ScorerKind.state_diff: state_diff_scorer,
    ScorerKind.privacy_check: privacy_check_scorer,
    ScorerKind.llm_judge: llm_judge_scorer,
}


def resolve_scorer(name: str, kind: ScorerKind) -> ScorerCallable | None:
    if name in SCORER_REGISTRY:
        return SCORER_REGISTRY[name]
    return KIND_DEFAULT_REGISTRY.get(kind)


__all__ = [
    "KIND_DEFAULT_REGISTRY",
    "SCORER_REGISTRY",
    "Scorer",
    "ScorerCallable",
    "exec_scorer",
    "file_diff_scorer",
    "llm_judge_scorer",
    "privacy_check_scorer",
    "readme_exact_scorer",
    "replay_unsupported",
    "resolve_scorer",
    "schema_scorer",
    "schema_validator_scorer",
    "score_to_verdict",
    "state_diff_scorer",
    "test_file_unchanged_scorer",
]
