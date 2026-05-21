"""State-diff scorer for vault/filesystem mutations."""

from __future__ import annotations

from typing import Any


def state_diff_scorer(*args: Any, **kwargs: Any) -> Any:
    from ab_datasets.schemas import ScorerKind, ScorerVerdict  # type: ignore[attr-defined]

    return ScorerVerdict(
        scorer_name="state_diff",
        kind=ScorerKind.state_diff,
        pass_=True,
        score=1.0,
        detail="stub",
    )
