"""LLM-judge scorer (must be paired with deterministic checks per LSN-004)."""

from __future__ import annotations

from typing import Any


def llm_judge_scorer(*args: Any, **kwargs: Any) -> Any:
    from ab_datasets.schemas import ScorerKind, ScorerVerdict  # type: ignore[attr-defined]

    return ScorerVerdict(
        scorer_name="llm_judge",
        kind=ScorerKind.llm_judge,
        pass_=True,
        score=1.0,
        detail="stub",
    )
