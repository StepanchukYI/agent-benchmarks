"""Validate trajectory JSONL invariants (build spec §6)."""

from __future__ import annotations

import json
from pathlib import Path

_VALID_STATUS = {"completed", "timeout", "unrunnable", "error"}


def validate(path: str | Path) -> list[str]:
    """Return a list of invariant violations; empty list means valid.

    Invariants enforced (build spec §6):
    - exactly one run_start and exactly one run_end
    - run_start is the first event, run_end is the last
    - turn.idx strictly monotonic from 0
    - run_end.status in {completed, timeout, unrunnable, error}
    - scorer events appear after the final turn
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

    turn_indices = [e.get("idx") for e in events if e.get("event") == "turn"]
    for expected, got in enumerate(turn_indices):
        if got != expected:
            issues.append(f"turn idx not monotonic from 0: expected {expected}, got {got}")
            break

    if ends:
        status = events[ends[0]].get("status")
        if status not in _VALID_STATUS:
            issues.append(f"run_end.status invalid: {status!r}")

    last_turn = max(
        (i for i, e in enumerate(events) if e.get("event") == "turn"), default=-1
    )
    for i, e in enumerate(events):
        if e.get("event") == "scorer" and i < last_turn:
            issues.append(f"scorer at index {i} appears before final turn at {last_turn}")

    return issues
