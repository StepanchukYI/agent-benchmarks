"""Deterministic scorer for the `tool_skill` pillar.

Signals are read from the trajectory file only — `run` and `replay` are
identical here because the relevant signal (tool_calls / tool_returns) lives
in the trajectory, not in the workdir.

Heuristic score (0-1):
  - start 1.0
  - subtract 0.5 if error_rate > 0.25 (errors / total_calls)
  - subtract 0.3 if redundant_ratio > 0.5 (consecutive duplicate (name,args))
  - subtract 0.2 if total_calls > max_tool_calls (default 50)
  - clamp to [0, 1]

Pass iff score >= pass_threshold (default 0.7).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import replay_unsupported, score_to_verdict


def _iter_turns(trajectory_path: Path):
    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") != "turn":
                continue
            yield ev


def _stable_args_key(args: Any) -> str:
    """Deterministic stringification of tool-call args for dedupe comparison."""
    try:
        return json.dumps(args, sort_keys=True, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return repr(args)


def _evaluate(
    trajectory_path: Path,
    *,
    max_tool_calls: int,
    pass_threshold: float,
) -> ScorerVerdict:
    name = "tool_skill"
    kind = ScorerKind.deterministic

    total_calls = 0
    error_calls = 0
    redundant_calls = 0
    prev_key: str | None = None
    breakdown_by_tool: dict[str, int] = {}

    for ev in _iter_turns(trajectory_path):
        for tc in ev.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            total_calls += 1
            tname = tc.get("name") or "<unknown>"
            breakdown_by_tool[str(tname)] = breakdown_by_tool.get(str(tname), 0) + 1
            args = tc.get("args") or tc.get("input") or {}
            key = f"{tname}::{_stable_args_key(args)}"
            if prev_key is not None and key == prev_key:
                redundant_calls += 1
            prev_key = key
        for ret in ev.get("tool_returns") or []:
            if not isinstance(ret, dict):
                continue
            if ret.get("is_error") is True:
                error_calls += 1

    error_rate = (error_calls / total_calls) if total_calls else 0.0
    redundant_ratio = (redundant_calls / total_calls) if total_calls else 0.0

    score = 1.0
    if error_rate > 0.25:
        score -= 0.5
    if redundant_ratio > 0.5:
        score -= 0.3
    if total_calls > max_tool_calls:
        score -= 0.2
    score = max(0.0, min(1.0, score))

    ok = score >= pass_threshold

    detail: dict[str, Any] = {
        "total_calls": total_calls,
        "error_calls": error_calls,
        "error_rate": round(error_rate, 6),
        "redundant_ratio": round(redundant_ratio, 6),
        "breakdown_by_tool": breakdown_by_tool,
        "max_tool_calls": max_tool_calls,
        "pass_threshold": pass_threshold,
    }
    return score_to_verdict(name, kind, ok, score, detail)


def tool_skill_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    max_tool_calls: int = 50,
    pass_threshold: float = 0.7,
    **_: Any,
) -> ScorerVerdict:
    name = "tool_skill"
    kind = ScorerKind.deterministic
    if trajectory_path is None:
        return replay_unsupported(name, kind, "trajectory_path required for tool_skill")
    return _evaluate(
        trajectory_path,
        max_tool_calls=int(max_tool_calls),
        pass_threshold=float(pass_threshold),
    )
