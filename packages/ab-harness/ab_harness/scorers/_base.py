"""Base Protocol/ABC for scorers + verdict helper.

Every deterministic scorer must accept either:
  - run(workdir, task, **scorer_config) -> ScorerVerdict
  - replay(trajectory_path, task, **scorer_config) -> ScorerVerdict
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Protocol, runtime_checkable

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task


@runtime_checkable
class Scorer(Protocol):
    name: str
    kind: ScorerKind

    def run(
        self,
        workdir: Path | None,
        task: Task,
        trajectory_path: Path | None = None,
        **scorer_config: Any,
    ) -> ScorerVerdict: ...

    def replay(
        self,
        trajectory_path: Path,
        task: Task,
        **scorer_config: Any,
    ) -> ScorerVerdict: ...


def score_to_verdict(
    name: str,
    kind: ScorerKind,
    ok: bool,
    score: float,
    detail: str | dict[str, Any],
) -> ScorerVerdict:
    return ScorerVerdict.model_validate(
        {
            "scorer_name": name,
            "kind": kind,
            "pass": ok,
            "score": score,
            "detail": detail,
        }
    )


def replay_unsupported(name: str, kind: ScorerKind, reason: str) -> ScorerVerdict:
    return score_to_verdict(
        name,
        kind,
        ok=False,
        score=0.0,
        detail={"replay_unsupported": True, "reason": reason},
    )
