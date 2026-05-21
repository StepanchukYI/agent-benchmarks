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
        assertions = cfg.get("assertions") or []
        # Pass scorer-level extras like `tool_schema_path` into the assertion
        # params under `_tool_schema_path` so `tool_args_match_schema` can find
        # the schema relative to fixture_dir.
        extra_context: dict[str, Any] = {}
        if cfg.get("tool_schema_path"):
            extra_context["tool_schema_path"] = cfg["tool_schema_path"]
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
