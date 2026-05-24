from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from sqlmodel import Session, select

from ab_server.fetcher.parser import ParsedRun
from ab_server.models import PromptBlob, RegisteredRepo, Submission, TaskResult
from ab_server.models.prompt_blob import _truncate

# Separator injected by ab_harness.runners.base.compose_system_prompt between
# the sandbox guardrail and the operator's custom CLAUDE.md text.
_CLAUDE_MD_MARKER = "\n\n--- project CLAUDE.md ---\n"


def _extract_custom_prompt(system_prompt_verbatim: str | None) -> str | None:
    """Return the clean operator CLAUDE.md text from a composed system prompt.

    Returns None when:
    - system_prompt_verbatim is absent (vanilla run, no custom prompt), or
    - the marker is not present (plain sandbox guardrail only — not a custom run).

    This keeps vanilla runs out of prompt_blobs and ensures the stored text is
    only the operator-authored content, not the harness preamble.
    """
    if not system_prompt_verbatim:
        return None
    idx = system_prompt_verbatim.find(_CLAUDE_MD_MARKER)
    if idx == -1:
        return None  # no custom CLAUDE.md — not a custom-prompt run
    return system_prompt_verbatim[idx + len(_CLAUDE_MD_MARKER):]


def _token_turn_counts(traj_path: Path) -> tuple[int, int, int, int]:
    """Extract (tokens_total, tokens_in, tokens_out, turns_total) from a trajectory.

    Source priority for tokens: the run_end ``totals`` block (the authoritative
    per-run aggregate). If a run_end has no totals, sum the per-turn tokens. If
    neither is present, fall back to the ``context_efficiency`` scorer verdict's
    ``detail.total_tokens``. Turn count is the number of assistant turns (the
    units a model is actually billed/measured on). Returns zeros for an
    unreadable/missing file rather than raising — ingest must stay idempotent.
    """
    if not traj_path.exists():
        return 0, 0, 0, 0

    totals_in: int | None = None
    totals_out: int | None = None
    sum_in = 0
    sum_out = 0
    assistant_turns = 0
    ce_total_tokens: int | None = None

    try:
        with traj_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                kind = ev.get("event")
                if kind == "turn":
                    sum_in += int(ev.get("tokens_in") or 0)
                    sum_out += int(ev.get("tokens_out") or 0)
                    if ev.get("role") == "assistant":
                        assistant_turns += 1
                elif kind == "run_end":
                    totals = ev.get("totals")
                    if isinstance(totals, dict):
                        totals_in = int(totals.get("tokens_in") or 0)
                        totals_out = int(totals.get("tokens_out") or 0)
                elif kind == "scorer" and ev.get("scorer_name") == "context_efficiency":
                    detail = ev.get("detail")
                    if isinstance(detail, dict) and detail.get("total_tokens") is not None:
                        ce_total_tokens = int(detail.get("total_tokens") or 0)
    except OSError:
        return 0, 0, 0, 0

    if totals_in is not None or totals_out is not None:
        t_in = totals_in or 0
        t_out = totals_out or 0
    elif sum_in or sum_out:
        t_in, t_out = sum_in, sum_out
    elif ce_total_tokens is not None:
        # Scorer detail only carries a combined total; we cannot split it.
        return ce_total_tokens, 0, 0, assistant_turns
    else:
        t_in, t_out = 0, 0

    return t_in + t_out, t_in, t_out, assistant_turns


def _config_from_trajectory(
    traj_path: Path,
) -> tuple[str | None, str | None, str | None, str | None]:
    """Extract (harness, effort, prompt_label, system_prompt_verbatim) from run_start.

    harness and prompt_label are top-level keys on run_start; effort is nested
    at reasoning.effort (reasoning may be null/absent);
    system_prompt_verbatim is the verbatim CLAUDE.md / operator prompt text
    (populated by BT3 when a custom prompt was active).

    Missing/unreadable file or no run_start event returns (None, None, None, None)
    — same defensive handling as _token_turn_counts.
    """
    if not traj_path.exists():
        return None, None, None, None
    try:
        with traj_path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if ev.get("event") == "run_start":
                    harness = ev.get("harness") or None
                    reasoning = ev.get("reasoning")
                    effort = reasoning.get("effort") if isinstance(reasoning, dict) else None
                    prompt_label = ev.get("prompt_label") or None
                    system_prompt_verbatim = ev.get("system_prompt_verbatim") or None
                    return harness, effort or None, prompt_label, system_prompt_verbatim
    except OSError:
        return None, None, None, None
    return None, None, None, None


def _upsert_prompt_blob(
    session: Session,
    *,
    prompt_hash: str,
    text: str,
    label: str | None,
) -> None:
    """Insert a PromptBlob row if the hash is not already present.

    Idempotent: a second call with the same prompt_hash is a no-op. The stored
    text is capped at 64 KB via _truncate (defined in models.prompt_blob).
    """
    existing = session.get(PromptBlob, prompt_hash)
    if existing is not None:
        return
    blob = PromptBlob(
        prompt_hash=prompt_hash,
        text=_truncate(text),
        label=label,
    )
    session.add(blob)
    session.commit()


def ingest_runs(
    session: Session,
    repo: RegisteredRepo,
    parsed_runs: Iterable[ParsedRun],
) -> tuple[int, int]:
    """Insert one Submission + one TaskResult per parsed run, idempotent."""
    inserted = 0
    skipped = 0
    for run in parsed_runs:
        existing = session.exec(
            select(Submission)
            .where(Submission.registered_repo_id == repo.id)
            .where(Submission.source_commit_sha == run.source_commit_sha)
            .where(Submission.source_path == run.source_path)
        ).first()
        if existing is not None:
            skipped += 1
            continue

        submission = Submission(
            registered_repo_id=repo.id,
            source_commit_sha=run.source_commit_sha,
            source_path=run.source_path,
            trust_tier="self_reported",
            model=run.model,
            tier=run.tier,
            dataset_version=run.dataset_version,
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)

        suite = str(run.metadata.get("suite") or run.scores.get("suite") or _suite_from_task(run.task_id))
        score_total = float(run.scores.get("total_score") or 0.0)
        # Per-pillar scores live in scores.json["per_pillar"] (written by the
        # local runner; key names match SCORER_PILLAR_MAP values). A key is
        # ABSENT when the task carried no scorer for that pillar — we store
        # None (not 0.0) so the leaderboard can tell "not measured" apart from
        # a genuine measured 0.0. A present value (including 0.0) is kept as-is.
        per_pillar = run.scores.get("per_pillar") or {}
        passed = _compute_passed(
            run.scores.get("verdicts") or [],
            total_score=run.scores.get("total_score"),
            per_pillar=per_pillar,
        )
        # Legacy status: derive from the top-level scores["pass"] bool exactly as
        # pre-B1 did — decoupled from the new tri-state `passed` (None = not measured).
        status_value = "passed" if bool(run.scores.get("pass")) else "failed"
        # Cost + latency come from the trajectory's run_end / cost_usd
        # aggregate — older ingest code read from metadata.yaml where they
        # weren't present. Fall back to scores.json fields too.
        cost_usd = float(
            run.metadata.get("cost_usd")
            or run.scores.get("cost_usd")
            or run.scores.get("total_cost_usd")
            or 0.0
        )
        latency_ms = int(
            run.metadata.get("latency_ms")
            or run.scores.get("latency_ms")
            or run.scores.get("total_latency_ms")
            or 0
        )
        tokens_total, tokens_in, tokens_out, turns_total = _token_turn_counts(
            run.path / "trajectory.jsonl"
        )
        harness, effort, prompt_label, system_prompt_verbatim = _config_from_trajectory(
            run.path / "trajectory.jsonl"
        )

        tier_hash_val = str(run.metadata.get("tier_hash") or "")
        # Upsert prompt blob only when a custom CLAUDE.md was active.
        # _extract_custom_prompt returns None for vanilla runs (no marker) so
        # the sandbox-guardrail-only text never lands in prompt_blobs.
        custom_text = _extract_custom_prompt(system_prompt_verbatim)
        if custom_text and tier_hash_val:
            _upsert_prompt_blob(
                session,
                prompt_hash=tier_hash_val,
                text=custom_text,
                label=prompt_label,
            )

        task_result = TaskResult(
            submission_id=submission.id,
            task_id=run.task_id,
            suite=suite,
            model=run.model,
            tier=run.tier,
            tier_hash=tier_hash_val,
            status=status_value,
            score_total=score_total,
            score_correctness=_pillar_score(per_pillar, "correctness"),
            score_context_eff=_pillar_score(per_pillar, "context_efficiency"),
            score_tool_skill=_pillar_score(per_pillar, "tool_skill"),
            score_memory=_pillar_score(per_pillar, "memory_specific"),
            score_latency=_pillar_score(per_pillar, "latency_cost"),
            cost_usd=cost_usd,
            latency_ms=latency_ms,
            tokens_total=tokens_total,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            turns_total=turns_total,
            trajectory_blob_ref=str(run.path / "trajectory.jsonl"),
            passed=passed,
            harness=harness,
            effort=effort,
            prompt_label=prompt_label,
        )
        session.add(task_result)
        session.commit()
        inserted += 1

    return inserted, skipped


def _compute_passed(
    verdicts: list,
    total_score: float | None = None,  # accepted for ABI back-compat, not used
    per_pillar: dict | None = None,    # accepted for ABI back-compat, not used
) -> bool | None:
    """Derive per-task pass flag from individual scorer verdicts (strict-AND).

    Semantics:
    - ``passed = all(v["pass"] for v in decided)`` where decided = verdicts with
      non-None ``pass``.
    - Returns None when zero decided verdicts ("not measured").

    Earlier this helper relaxed pass to ``total_score >= 0.5`` (B2). That turned
    out to inflate the leaderboard — partial runs with one objectively-failed
    scorer were marked pass and bumped pass-rates near 100%. After B1 (stub-
    tool exposure) and B3 (CRLF normalization) relaxed the sub-scorers
    themselves, strict-AND is honest again: a fail means a scorer genuinely
    decided this run did not meet its acceptance criterion.

    ``total_score`` and ``per_pillar`` are accepted so existing call sites
    don't have to change, but they DON'T influence the returned pass — the
    binary chain is the source of truth.

    Individual scorer pass/fail values stay untouched so the drill view still
    shows WHICH scorer failed.

    The verdict wire format uses "pass" as the key (Python reserved word;
    Pydantic aliases pass_ ↔ "pass"). We read it defensively from the raw
    dict so this helper works on parsed dicts from scores.json.
    """
    decided: list[bool] = []
    for v in verdicts:
        if not isinstance(v, dict):
            continue
        # "pass" is the wire key; some paths write "pass_" — check both.
        val = v.get("pass") if "pass" in v else v.get("pass_")
        if val is None:
            continue
        decided.append(bool(val))
    if not decided:
        return None
    return all(decided)


def _pillar_score(per_pillar: dict, key: str) -> float | None:
    """Return the measured pillar score, or None when the key is absent.

    None means "not measured" (task carried no scorer for this pillar); a
    present value, including a genuine 0.0, is kept so the leaderboard can tell
    a real zero apart from missing data.
    """
    val = per_pillar.get(key)
    return float(val) if val is not None else None


def _suite_from_task(task_id: str) -> str:
    if "_" in task_id:
        return task_id.rsplit("_", 1)[0]
    return task_id
