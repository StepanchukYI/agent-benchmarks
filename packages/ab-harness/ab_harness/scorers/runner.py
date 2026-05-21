"""Scorer chain runner.

Iterates `task.scorer_chain`, dispatches each via the registry.
- mode="replay" forces trajectory-only execution.
- mode="run" prefers live workdir; falls back to replay if no workdir given.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerVerdict, Task

from ab_harness.scorers import resolve_scorer
from ab_harness.scorers._base import score_to_verdict

_log = logging.getLogger(__name__)


def run_scorer_chain(
    task: Task,
    trajectory_path: Path | None = None,
    workdir: Path | None = None,
    mode: str = "run",
) -> list[ScorerVerdict]:
    if mode not in {"run", "replay"}:
        raise ValueError(f"mode must be 'run' or 'replay', got {mode!r}")

    effective_mode = mode
    if effective_mode == "run" and workdir is None:
        effective_mode = "replay"

    verdicts: list[ScorerVerdict] = []
    for spec in task.scorer_chain:
        scorer = resolve_scorer(spec.name, spec.kind)
        if scorer is None:
            verdicts.append(
                score_to_verdict(
                    spec.name,
                    spec.kind,
                    ok=False,
                    score=0.0,
                    detail={"error": f"no scorer registered for name={spec.name!r} kind={spec.kind}"},
                )
            )
            continue

        kwargs: dict[str, Any] = dict(spec.config or {})
        kwargs["mode"] = effective_mode

        try:
            verdict = scorer(
                workdir=workdir if effective_mode == "run" else None,
                task=task,
                trajectory_path=trajectory_path,
                **kwargs,
            )
        except Exception as exc:
            _log.exception("scorer %s raised", spec.name)
            verdict = score_to_verdict(
                spec.name,
                spec.kind,
                ok=False,
                score=0.0,
                detail={"error": f"{type(exc).__name__}: {exc}"},
            )

        if not isinstance(verdict, ScorerVerdict):
            verdict = score_to_verdict(
                spec.name,
                spec.kind,
                ok=False,
                score=0.0,
                detail={"error": f"scorer returned non-ScorerVerdict: {type(verdict).__name__}"},
            )
        verdicts.append(verdict)

    return verdicts
