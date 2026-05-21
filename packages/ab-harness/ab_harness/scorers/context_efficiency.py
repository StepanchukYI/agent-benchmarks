"""Deterministic scorer for the `context_efficiency` pillar.

Reads tokens_in + tokens_out from each turn. Lower total = higher score.

Score (0-1):
  - total_tokens <= target_tokens: 1.0
  - total_tokens <= max_tokens:    linear decay from 1.0 to 0.0
  - else:                          0.0

Pass iff score >= pass_threshold (default 0.5).
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


def _linear_decay(value: float, target: float, max_value: float) -> float:
    if value <= target:
        return 1.0
    if value >= max_value:
        return 0.0
    span = max_value - target
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, 1.0 - (value - target) / span))


def _evaluate(
    trajectory_path: Path,
    *,
    target_tokens: int,
    max_tokens: int,
    pass_threshold: float,
) -> ScorerVerdict:
    name = "context_efficiency"
    kind = ScorerKind.deterministic

    total_tokens = 0
    total_assistant_turns = 0
    for ev in _iter_turns(trajectory_path):
        tokens_in = int(ev.get("tokens_in") or 0)
        tokens_out = int(ev.get("tokens_out") or 0)
        total_tokens += tokens_in + tokens_out
        if ev.get("role") == "assistant":
            total_assistant_turns += 1

    score = _linear_decay(float(total_tokens), float(target_tokens), float(max_tokens))
    avg = (total_tokens / total_assistant_turns) if total_assistant_turns else 0.0
    ok = score >= pass_threshold

    detail: dict[str, Any] = {
        "total_tokens": total_tokens,
        "total_assistant_turns": total_assistant_turns,
        "avg_tokens_per_turn": round(avg, 4),
        "target_tokens": target_tokens,
        "max_tokens": max_tokens,
        "pass_threshold": pass_threshold,
    }
    return score_to_verdict(name, kind, ok, score, detail)


def context_efficiency_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    target_tokens: int = 1000,
    max_tokens: int = 10000,
    pass_threshold: float = 0.5,
    **_: Any,
) -> ScorerVerdict:
    name = "context_efficiency"
    kind = ScorerKind.deterministic
    if trajectory_path is None:
        return replay_unsupported(name, kind, "trajectory_path required for context_efficiency")
    return _evaluate(
        trajectory_path,
        target_tokens=int(target_tokens),
        max_tokens=int(max_tokens),
        pass_threshold=float(pass_threshold),
    )
