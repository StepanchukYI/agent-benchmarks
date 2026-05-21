"""Scorer implementations: deterministic, schema, exec, llm-judge, state-diff, privacy-check.

The registry is keyed by (kind, name) AND (name) — the chain runner dispatches
on the `kind` first (from `ScorerSpec.kind`), then falls back to looking up by name.
"""

from __future__ import annotations

from collections.abc import Callable

from ab_datasets.schemas import ScorerKind

from ab_harness.scorers._base import Scorer, replay_unsupported, score_to_verdict
from ab_harness.scorers.context_efficiency import context_efficiency_scorer
from ab_harness.scorers.deterministic import (
    exec_scorer,
    file_diff_scorer,
    schema_validator_scorer,
)
from ab_harness.scorers.file_invariants import (
    readme_exact_scorer,
    test_file_unchanged_scorer,
)
from ab_harness.scorers.latency_cost import latency_cost_scorer
from ab_harness.scorers.llm_judge import llm_judge_scorer
from ab_harness.scorers.memory_check import memory_check_scorer
from ab_harness.scorers.privacy_check import privacy_check_scorer
from ab_harness.scorers.schema import schema_scorer
from ab_harness.scorers.state_diff import state_diff_scorer
from ab_harness.scorers.tool_skill import tool_skill_scorer

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
    "tool_skill": tool_skill_scorer,
    "context_efficiency": context_efficiency_scorer,
    "latency_cost": latency_cost_scorer,
    "memory_check": memory_check_scorer,
}

KIND_DEFAULT_REGISTRY: dict[ScorerKind, ScorerCallable] = {
    ScorerKind.exec: exec_scorer,
    ScorerKind.schema: schema_scorer,
    ScorerKind.state_diff: state_diff_scorer,
    ScorerKind.privacy_check: privacy_check_scorer,
    ScorerKind.llm_judge: llm_judge_scorer,
}


# Maps registered scorer name -> task `weights:` pillar.
# Used by ab_sdk.results.build_scores_payload to compute the weighted
# total_score and per-pillar breakdown. Scorers not listed here default
# to the "correctness" pillar (treat unknowns as correctness signals
# rather than dropping them on the floor).
#
# privacy_check is mapped to "correctness" intentionally: privacy is a
# hard gate, not an axis with its own weight. The pillar membership only
# influences total_score; the gate itself lives in the publish path.
SCORER_PILLAR_MAP: dict[str, str] = {
    "file_diff": "correctness",
    "schema": "correctness",
    "schema_validator": "correctness",
    "exec": "correctness",
    "readme_exact": "correctness",
    "test_file_unchanged": "correctness",
    "state_diff": "correctness",
    "privacy_check": "correctness",
    "llm_judge": "correctness",
    "tool_skill": "tool_skill",
    "context_efficiency": "context_efficiency",
    "latency_cost": "latency_cost",
    "memory_check": "memory_specific",
    "memory_specific": "memory_specific",
}


def resolve_scorer(name: str, kind: ScorerKind) -> ScorerCallable | None:
    if name in SCORER_REGISTRY:
        return SCORER_REGISTRY[name]
    return KIND_DEFAULT_REGISTRY.get(kind)


def pillar_for(scorer_name: str) -> str:
    """Return the pillar a scorer contributes to. Defaults to 'correctness'."""
    return SCORER_PILLAR_MAP.get(scorer_name, "correctness")


__all__ = [
    "KIND_DEFAULT_REGISTRY",
    "SCORER_PILLAR_MAP",
    "SCORER_REGISTRY",
    "Scorer",
    "ScorerCallable",
    "context_efficiency_scorer",
    "exec_scorer",
    "file_diff_scorer",
    "latency_cost_scorer",
    "llm_judge_scorer",
    "memory_check_scorer",
    "pillar_for",
    "privacy_check_scorer",
    "readme_exact_scorer",
    "replay_unsupported",
    "resolve_scorer",
    "schema_scorer",
    "schema_validator_scorer",
    "score_to_verdict",
    "state_diff_scorer",
    "test_file_unchanged_scorer",
    "tool_skill_scorer",
]
