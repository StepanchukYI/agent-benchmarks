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
from ab_harness.scorers.privacy_check import privacy_check_scorer
from ab_harness.scorers.schema import schema_scorer
from ab_harness.scorers.state_diff import state_diff_scorer
from ab_harness.scorers.tool_skill import tool_skill_scorer
from ab_harness.scorers.track_b_scorers import TRACK_B_SCORERS

ScorerCallable = Callable[..., object]

SCORER_REGISTRY: dict[str, ScorerCallable] = {
    "file_diff": file_diff_scorer,
    "exec": exec_scorer,
    "schema": schema_scorer,
    "schema_validator": schema_scorer,
    # L0_016..L0_019 schema-fill backlog: each task pins a value-equality
    # check on its filled JSON file. Same underlying impl (schema_scorer in
    # `mode: json_value_equals`), distinct names so the per-scorer verdict
    # in the trajectory is human-meaningful.
    "profile_value_equals": schema_scorer,
    "manifest_value_equals": schema_scorer,
    "task_value_equals": schema_scorer,
    "event_value_equals": schema_scorer,
    "state_diff": state_diff_scorer,
    "privacy_check": privacy_check_scorer,
    "llm_judge": llm_judge_scorer,
    "test_file_unchanged": test_file_unchanged_scorer,
    "readme_exact": readme_exact_scorer,
    "tool_skill": tool_skill_scorer,
    "context_efficiency": context_efficiency_scorer,
    "latency_cost": latency_cost_scorer,
    # Track B assertion-chain scorers (~30 names that share one engine).
    **TRACK_B_SCORERS,
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
    "profile_value_equals": "correctness",
    "manifest_value_equals": "correctness",
    "task_value_equals": "correctness",
    "event_value_equals": "correctness",
    "exec": "correctness",
    "readme_exact": "correctness",
    "test_file_unchanged": "correctness",
    "state_diff": "correctness",
    "privacy_check": "correctness",
    "llm_judge": "correctness",
    "tool_skill": "tool_skill",
    "context_efficiency": "context_efficiency",
    "latency_cost": "latency_cost",
    # memory_check and other L1+ scorers are added by task-authoring agents
    # alongside their L1+ task YAMLs. This file is the central registry;
    # entries land here when those tasks land.
    "memory_specific": "memory_specific",
    # ----- Track B assertion-chain scorers -----
    # Tool-skill-pillar entries: scorers that primarily probe tool-call
    # discipline (calling shape, arg fidelity, skill dispatch).
    "tool_call_validator": "tool_skill",
    "refuse_tool_call_check": "tool_skill",
    "skill_dispatched_check": "tool_skill",
    "no_fake_skill_check": "tool_skill",
    "first_read_is_operator_file": "tool_skill",
    "ask_before_destructive_check": "tool_skill",
    # Everything else from Track B contributes to correctness.
    "abstention_check": "correctness",
    "cite_correct_paragraph_check": "correctness",
    "contradiction_reported_check": "correctness",
    "error_handling_check": "correctness",
    "exact_answer_check": "correctness",
    "exact_block_check": "correctness",
    "exact_codes_check": "correctness",
    "exact_output_check": "correctness",
    "exact_passphrase_check": "correctness",
    "exact_sum_check": "correctness",
    "factual_constant_check": "correctness",
    "final_state_check": "correctness",
    "idempotency_check": "correctness",
    "json_only_check": "correctness",
    "no_emoji_check": "correctness",
    "no_invented_rules_check": "correctness",
    "preserved_name_and_version": "correctness",
    "pytest_exec": "correctness",
    "quote_attribution_check": "correctness",
    "rule_followed_check": "correctness",
    "utf8_exact_bytes": "correctness",
    "verbatim_citation_check": "correctness",
    "word_count_check": "correctness",
    # ----- L0_011..L0_710 batch (49 names). Tool-skill axis: validators
    # that primarily check tool-call shape (args, ordering, dispatch).
    # Everything else lands on the correctness pillar.
    "base64_args_validator": "tool_skill",
    "nested_args_validator": "tool_skill",
    "pagination_validator": "tool_skill",
    "parallel_calls_validator": "tool_skill",
    "retry_validator": "tool_skill",
    "right_tool_picked": "tool_skill",
    "state_tracking_validator": "tool_skill",
    "tool_dispatched_check": "tool_skill",
    "no_fake_invocation_check": "tool_skill",
    "rule_gates_tool_check": "tool_skill",
    "skill_invocation_check": "tool_skill",
    "exec_skill_dispatched": "tool_skill",
    "lifecycle_order_check": "tool_skill",
    "exec_silence_check": "tool_skill",
    # Correctness — verdicts, content checks, exact-match shapes,
    # state assertions, hallucination/source-quality checks.
    "best_source_verdict": "correctness",
    "cached_hit_check": "correctness",
    "consistency_verdict": "correctness",
    "correct_attribution_check": "correctness",
    "crlf_preserved_diff": "correctness",
    "exact_arrival_time": "correctness",
    "exact_assignment": "correctness",
    "exact_bool": "correctness",
    "exact_boolean": "correctness",
    "exact_chain": "correctness",
    "exact_code_check": "correctness",
    "exact_count": "correctness",
    "exact_csv_line": "correctness",
    "exact_date": "correctness",
    "exact_founders_check": "correctness",
    "exact_json_pretty": "correctness",
    "exact_multi_key_check": "correctness",
    "exact_number": "correctness",
    "exact_pair_check": "correctness",
    "exact_percentage": "correctness",
    "exact_signers_check": "correctness",
    "exact_top5_check": "correctness",
    "exact_verdict": "correctness",
    "forbidden_substrings_check": "correctness",
    "greek_alphabet_check": "correctness",
    "hallucination_identified": "correctness",
    "implicit_decline_check": "correctness",
    "json_semantic_equivalent": "correctness",
    "json_structure_check": "correctness",
    "multi_constraint_check": "correctness",
    "must_not_contain_check": "correctness",
    "nested_batch_state": "correctness",
    "override_check": "correctness",
    "per_source_verdict": "correctness",
    "rotated_state": "correctness",
    "rule_precedence_check": "correctness",
    "scoped_diff": "correctness",
    "stale_flag_verdict": "correctness",
    "t3_strict_no_emoji": "correctness",
    # L1/L4 memory-specific checks.
    "decision_schema_validator": "memory_specific",
    "lesson_schema_validator": "memory_specific",
    "append_only_state_diff": "memory_specific",
    "lesson_append_only": "memory_specific",
    "importance_distribution_check": "memory_specific",
    "multi_decision_state_diff": "memory_specific",
    "vault_state_diff": "memory_specific",
    # L4 SWE/composite correctness checks.
    "red_green_exec": "correctness",
    "minimal_patch_state_diff": "correctness",
    "hallucination_check": "correctness",
}


def resolve_scorer(name: str, kind: ScorerKind) -> ScorerCallable | None:
    if kind in KIND_DEFAULT_REGISTRY:
        return KIND_DEFAULT_REGISTRY[kind]
    return SCORER_REGISTRY.get(name)


def pillar_for(scorer_name: str) -> str:
    """Return the pillar a scorer contributes to. Defaults to 'correctness'."""
    return SCORER_PILLAR_MAP.get(scorer_name, "correctness")


__all__ = [
    "KIND_DEFAULT_REGISTRY",
    "SCORER_PILLAR_MAP",
    "SCORER_REGISTRY",
    "TRACK_B_SCORERS",
    "Scorer",
    "ScorerCallable",
    "context_efficiency_scorer",
    "exec_scorer",
    "file_diff_scorer",
    "latency_cost_scorer",
    "llm_judge_scorer",
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
