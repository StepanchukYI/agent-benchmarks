"""Thin wrapper scorers for the Track-B assertion-chain pattern.

Track B's task YAML uses ~30 scorer *names* that all share the same shape:

    - name: <scorer_name>
      kind: deterministic
      config:
        assertions:
          - kind: <assertion_kind>
            ...kind-specific params...

Each wrapper here is a 5-line glue layer: load trajectory events, resolve the
fixture dir, hand control to `run_assertion_chain`. Differentiating them by
*name* (rather than collapsing them all into one) keeps `ScorerVerdict.scorer_name`
informative in the trajectory and lets the pillar map route them per-name.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import score_to_verdict
from ab_harness.scorers.assertions import load_events, run_assertion_chain


def _resolve_fixture_dir(task: Task | None) -> Path | None:
    if task is None or not task.fixture_ref:
        return None
    # Use ab-cli's discover helpers when present; fall back gracefully if not.
    try:
        from ab_cli._discover import fixture_dir_for_task  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        return fixture_dir_for_task(task)
    except (RuntimeError, OSError):
        return None


def _expand_shorthand_to_assertions(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    """Translate Track B's file_diff-style shortcut config into assertions.

    Several L0 task YAMLs (L0_009, L0_010, L0_012, ...) use a compact shape:

        config:
          expected:
            <path>: "<bytes>"
          must_be_absent:
            - <path>
          forbid_bom: true
          forbid_crlf: true
          preserve_crlf: true        # opposite — assert CRLF present
          encoding: "utf-8"

    Convert that into the explicit `assertions: [...]` form so the
    assertion-chain dispatcher can process them. Idempotent: returns `[]`
    when no shorthand keys are present.
    """
    out: list[dict[str, Any]] = []
    expected = cfg.get("expected") or {}
    if isinstance(expected, dict):
        for path, content in expected.items():
            out.append({
                "kind": "workdir_file_content_equals",
                "path": path,
                "content": content,
                "encoding": cfg.get("encoding", "utf-8"),
            })
    must_be_absent = cfg.get("must_be_absent") or []
    for path in must_be_absent or []:
        out.append({"kind": "workdir_file_absent", "path": path})
    must_exist = cfg.get("must_exist") or []
    for path in must_exist or []:
        out.append({"kind": "workdir_file_exists", "path": path})
    forbidden = cfg.get("forbidden_substrings") or cfg.get("forbidden") or []
    target_path = cfg.get("target_path") or cfg.get("path")
    if target_path and forbidden:
        out.append({
            "kind": "workdir_file_does_not_contain",
            "path": target_path,
            "forbidden_substrings": forbidden,
            "encoding": cfg.get("encoding", "utf-8"),
        })
    if cfg.get("forbid_bom") and isinstance(expected, dict):
        for path in expected:
            out.append({"kind": "workdir_file_no_bom", "path": path})
    if cfg.get("forbid_crlf") and isinstance(expected, dict):
        for path in expected:
            out.append({"kind": "workdir_file_no_crlf", "path": path})
    if cfg.get("preserve_crlf") and isinstance(expected, dict):
        for path in expected:
            out.append({"kind": "workdir_file_preserves_crlf", "path": path})
    if cfg.get("require_utf8") and isinstance(expected, dict):
        for path in expected:
            out.append({"kind": "workdir_file_encoding_utf8", "path": path})
    return out


def _make_assertion_scorer(scorer_name: str):
    """Build a wrapper that runs Track B's assertion chain.

    The returned callable matches the ScorerCallable signature accepted by
    `ab_harness.scorers.runner.run_scorer_chain`.
    """

    def _scorer(
        workdir: Path | None = None,
        task: Task | None = None,
        trajectory_path: Path | None = None,
        *,
        mode: str = "run",
        **cfg: Any,
    ) -> ScorerVerdict:
        if trajectory_path is None:
            # Track B's deterministic scorers operate on the trajectory only.
            return score_to_verdict(
                scorer_name,
                ScorerKind.deterministic,
                ok=False,
                score=0.0,
                detail={"error": "trajectory_path required for Track-B scorers"},
            )
        events = load_events(trajectory_path)
        fixture_dir = _resolve_fixture_dir(task)
        assertions = list(cfg.get("assertions") or [])
        # Auto-expand file_diff-style shorthand (expected/must_be_absent/
        # encoding/forbid_*) into explicit workdir_file_* assertions so
        # YAMLs don't need to spell out every check. Useful for L0_009/
        # L0_010/L0_012 batch.
        if not assertions:
            assertions = _expand_shorthand_to_assertions(cfg)
        # Pass scorer-level extras like `tool_schema_path` into the assertion
        # params under `_tool_schema_path` so `tool_args_match_schema` can find
        # the schema relative to fixture_dir.
        extra_context: dict[str, Any] = {}
        if cfg.get("tool_schema_path"):
            extra_context["tool_schema_path"] = cfg["tool_schema_path"]
        if cfg.get("target_file"):
            extra_context["target_file"] = cfg["target_file"]
        if cfg.get("target_paths"):
            extra_context["target_paths"] = cfg["target_paths"]
        return run_assertion_chain(
            scorer_name,
            events,
            workdir,
            fixture_dir,
            assertions,
            extra_context=extra_context,
        )

    _scorer.__name__ = f"{scorer_name}_scorer"
    _scorer.__qualname__ = _scorer.__name__
    return _scorer


# The full list of Track B scorer names — must stay in sync with
# `- name:` entries in `packages/ab-datasets/ab_datasets/L0_foundation/*.yaml`.
# Six existing scorers (file_diff, schema_validator, tool_skill, privacy_check,
# context_efficiency, latency_cost) are NOT redefined here — they keep their
# native implementations.
TRACK_B_SCORER_NAMES: tuple[str, ...] = (
    "abstention_check",
    "ask_before_destructive_check",
    "cite_correct_paragraph_check",
    "contradiction_reported_check",
    "error_handling_check",
    "exact_answer_check",
    "exact_block_check",
    "exact_codes_check",
    "exact_output_check",
    "exact_passphrase_check",
    "exact_sum_check",
    "factual_constant_check",
    "final_state_check",
    "first_read_is_operator_file",
    "idempotency_check",
    "json_only_check",
    "no_emoji_check",
    "no_fake_skill_check",
    "no_invented_rules_check",
    "preserved_name_and_version",
    "pytest_exec",
    "quote_attribution_check",
    "refuse_tool_call_check",
    "rule_followed_check",
    "skill_dispatched_check",
    "tool_call_validator",
    "utf8_exact_bytes",
    "verbatim_citation_check",
    "word_count_check",
    # ----- L0_005, L0_011..L0_015, L0_104..L0_110, L0_309..L0_315,
    #       L0_404..L0_407, L0_502, L0_506..L0_510, L0_605..L0_606,
    #       L0_609..L0_615, L0_701..L0_710 batch -----
    # Each name follows the same assertion-chain pattern: the YAML's
    # `assertions:` block carries the per-task verdict logic. Adding the
    # name here wires it into the dispatcher; no per-task code is needed
    # in this file.
    "base64_args_validator",
    "best_source_verdict",
    "cached_hit_check",
    "consistency_verdict",
    "correct_attribution_check",
    "crlf_preserved_diff",
    "exact_arrival_time",
    "exact_assignment",
    "exact_bool",
    "exact_boolean",
    "exact_chain",
    "exact_code_check",
    "exact_count",
    "exact_csv_line",
    "exact_date",
    "exact_founders_check",
    "exact_json_pretty",
    "exact_multi_key_check",
    "exact_number",
    "exact_pair_check",
    "exact_percentage",
    "exact_signers_check",
    "exact_top5_check",
    "exact_verdict",
    "forbidden_substrings_check",
    "greek_alphabet_check",
    "hallucination_identified",
    "implicit_decline_check",
    "json_semantic_equivalent",
    "json_structure_check",
    "multi_constraint_check",
    "must_not_contain_check",
    "nested_args_validator",
    "nested_batch_state",
    "no_fake_invocation_check",
    "override_check",
    "pagination_validator",
    "parallel_calls_validator",
    "per_source_verdict",
    "retry_validator",
    "right_tool_picked",
    "rotated_state",
    "rule_gates_tool_check",
    "rule_precedence_check",
    "scoped_diff",
    "stale_flag_verdict",
    "state_tracking_validator",
    "t3_strict_no_emoji",
    "tool_dispatched_check",
    # L1-L3 deterministic assertion-chain aliases.
    "importance_distribution_check",
    "skill_invocation_check",
    "lifecycle_order_check",
)


# Materialize one callable per name and expose at module scope so the registry
# in `__init__.py` can import them by attribute.
TRACK_B_SCORERS: dict[str, Any] = {
    name: _make_assertion_scorer(name) for name in TRACK_B_SCORER_NAMES
}

# Side-effect: bind each scorer onto the module namespace so existing import
# patterns work (`from ab_harness.scorers.track_b_scorers import ...`).
for _n, _fn in TRACK_B_SCORERS.items():
    globals()[f"{_n}_scorer"] = _fn


__all__ = [
    "TRACK_B_SCORERS",
    "TRACK_B_SCORER_NAMES",
] + [f"{n}_scorer" for n in TRACK_B_SCORER_NAMES]
