"""Validate trajectory JSONL invariants (build spec §6)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_VALID_STATUS = {"completed", "timeout", "unrunnable", "error"}
_REQUIRED_TURN_FIELDS = ("tokens_in", "tokens_out", "latency_ms", "cost_usd")


def validate(path: str | Path, scorer_chain: list[Any] | None = None) -> list[str]:
    """Return a list of invariant violations; empty list means valid.

    Invariants enforced (build spec §6):
    1. exactly one run_start (first event) and one run_end (last event)
    2. run_end.status in {completed, timeout, unrunnable, error}
    3. turn.idx strictly monotonic from 0
    4. each turn has tool_calls/tool_returns as arrays + numeric tokens/latency/cost present
    5. scorers appear strictly after the final turn
    6. when scorer_chain is supplied, scorer order matches the chain
    """
    issues: list[str] = []
    p = Path(path)
    if not p.exists():
        return [f"file not found: {p}"]

    events: list[dict] = []
    for lineno, raw in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
        if not raw.strip():
            continue
        try:
            events.append(json.loads(raw))
        except json.JSONDecodeError as exc:
            issues.append(f"line {lineno}: invalid JSON: {exc}")

    if not events:
        return ["no events found"]

    starts = [i for i, e in enumerate(events) if e.get("event") == "run_start"]
    ends = [i for i, e in enumerate(events) if e.get("event") == "run_end"]
    if len(starts) != 1:
        issues.append(f"expected exactly one run_start, found {len(starts)}")
    if len(ends) != 1:
        issues.append(f"expected exactly one run_end, found {len(ends)}")
    if starts and starts[0] != 0:
        issues.append("run_start must be the first event")
    if ends and ends[0] != len(events) - 1:
        issues.append("run_end must be the last event")

    turn_positions = [i for i, e in enumerate(events) if e.get("event") == "turn"]
    for expected_idx, pos in enumerate(turn_positions):
        got = events[pos].get("idx")
        if got != expected_idx:
            issues.append(
                f"turn idx not monotonic from 0: expected {expected_idx}, got {got!r}"
            )
            break

    for pos in turn_positions:
        turn = events[pos]
        tc = turn.get("tool_calls")
        tr = turn.get("tool_returns")
        if not isinstance(tc, list):
            issues.append(f"turn idx={turn.get('idx')}: tool_calls must be a list, got {type(tc).__name__}")
        if not isinstance(tr, list):
            issues.append(f"turn idx={turn.get('idx')}: tool_returns must be a list, got {type(tr).__name__}")
        for field in _REQUIRED_TURN_FIELDS:
            if field not in turn:
                issues.append(f"turn idx={turn.get('idx')}: missing required field {field!r}")
        vd = turn.get("vault_state_diff", None)
        if vd is not None and (
            not isinstance(vd, dict)
            or not {"created", "modified", "deleted"} <= set(vd.keys())
        ):
            issues.append(
                f"turn idx={turn.get('idx')}: vault_state_diff must be null or "
                "{created,modified,deleted}"
            )

    if ends:
        status = events[ends[0]].get("status")
        if status not in _VALID_STATUS:
            issues.append(f"run_end.status invalid: {status!r}")

    last_turn = turn_positions[-1] if turn_positions else -1
    for i, e in enumerate(events):
        if e.get("event") == "scorer" and i <= last_turn:
            issues.append(f"scorer at index {i} appears before/at final turn at {last_turn}")

    if scorer_chain:
        expected_names = [
            (getattr(spec, "name", None) or spec.get("name") if isinstance(spec, dict) else getattr(spec, "name", None))
            for spec in scorer_chain
        ]
        got_names = [e.get("scorer") for e in events if e.get("event") == "scorer"]
        if got_names[: len(expected_names)] != expected_names:
            issues.append(
                f"scorer order mismatch: expected {expected_names!r}, got {got_names!r}"
            )

    return issues
