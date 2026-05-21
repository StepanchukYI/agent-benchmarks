"""Deterministic scorer for the `latency_cost` pillar.

Reads latency_ms and cost_usd from each turn.

Latency score (0-1):
  - total_latency_ms <= target_ms: 1.0
  - total_latency_ms <= max_ms:    linear decay from 1.0 to 0.0
  - else:                          0.0

Cost score: only computed if `max_cost_usd` is configured and total_cost_usd > 0.
When applicable, cost score is also a linear decay using target_cost_usd
(defaults to 0 if unset) and max_cost_usd. The final score is
min(latency_score, cost_score); otherwise just latency_score.

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
    target_ms: int,
    max_ms: int,
    pass_threshold: float,
    target_cost_usd: float | None,
    max_cost_usd: float | None,
) -> ScorerVerdict:
    name = "latency_cost"
    kind = ScorerKind.deterministic

    total_latency_ms = 0
    total_cost_usd = 0.0
    for ev in _iter_turns(trajectory_path):
        total_latency_ms += int(ev.get("latency_ms") or 0)
        total_cost_usd += float(ev.get("cost_usd") or 0.0)

    latency_score = _linear_decay(float(total_latency_ms), float(target_ms), float(max_ms))

    cost_score: float | None = None
    if max_cost_usd is not None and total_cost_usd > 0:
        tgt = float(target_cost_usd) if target_cost_usd is not None else 0.0
        cost_score = _linear_decay(total_cost_usd, tgt, float(max_cost_usd))

    score = latency_score if cost_score is None else min(latency_score, cost_score)
    ok = score >= pass_threshold

    detail: dict[str, Any] = {
        "total_latency_ms": total_latency_ms,
        "total_cost_usd": round(total_cost_usd, 8),
        "latency_score": round(latency_score, 6),
        "cost_score": (None if cost_score is None else round(cost_score, 6)),
        "target_ms": target_ms,
        "max_ms": max_ms,
        "target_cost_usd": target_cost_usd,
        "max_cost_usd": max_cost_usd,
        "pass_threshold": pass_threshold,
    }
    return score_to_verdict(name, kind, ok, score, detail)


def latency_cost_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    target_ms: int = 10000,
    max_ms: int = 120000,
    pass_threshold: float = 0.5,
    max_cost_usd: float | None = None,
    target_cost_usd: float | None = None,
    **_: Any,
) -> ScorerVerdict:
    name = "latency_cost"
    kind = ScorerKind.deterministic
    if trajectory_path is None:
        return replay_unsupported(name, kind, "trajectory_path required for latency_cost")
    return _evaluate(
        trajectory_path,
        target_ms=int(target_ms),
        max_ms=int(max_ms),
        pass_threshold=float(pass_threshold),
        target_cost_usd=(None if target_cost_usd is None else float(target_cost_usd)),
        max_cost_usd=(None if max_cost_usd is None else float(max_cost_usd)),
    )
