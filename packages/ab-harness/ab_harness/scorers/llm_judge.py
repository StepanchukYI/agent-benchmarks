"""LLM-judge scorer stub.

Phase 1 row 3 only ships deterministic scorers. LLM-judge is later.
Always returns pass_=True, score=1.0 with a clear stub log line.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import score_to_verdict

_log = logging.getLogger(__name__)


def llm_judge_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    **scorer_config: Any,
) -> ScorerVerdict:
    _log.info(
        "llm_judge_scorer stub invoked (mode=%s, task=%s, config_keys=%s) — Phase 1 ships deterministic scorers only",
        mode,
        getattr(task, "id", None),
        sorted(scorer_config),
    )
    return score_to_verdict(
        "llm_judge",
        ScorerKind.llm_judge,
        ok=True,
        score=1.0,
        detail={"stub": True},
    )
