"""Replay helper — re-run scorer chain over a recorded trajectory."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict


def _advisory(reason: str, run_dir: Path) -> list[ScorerVerdict]:
    return [
        ScorerVerdict(
            scorer_name="replay_advisory",
            kind=ScorerKind.deterministic,
            pass_=False,
            score=0.0,
            detail={
                "advisory": True,
                "reason": reason,
                "run_dir": str(run_dir),
            },
        )
    ]


def _coerce_task(scorer_chain: Any) -> Any:
    """Accept a Task, a list of ScorerSpec, or None; return a Task or None."""
    from ab_datasets.schemas import (
        Difficulty,
        Layer,
        ScorerSpec,
        Task,
        TaskConfig,
        TrustTier,
        Visibility,
    )

    if scorer_chain is None:
        return None
    if isinstance(scorer_chain, Task):
        return scorer_chain
    if isinstance(scorer_chain, list):
        specs: list[ScorerSpec] = []
        for item in scorer_chain:
            if isinstance(item, ScorerSpec):
                specs.append(item)
            elif isinstance(item, dict):
                specs.append(ScorerSpec.model_validate(item))
        return Task(
            id="replay-synthetic",
            layer=Layer.L0,
            suite="replay",
            title="replay",
            description="synthetic task for replay",
            scorer_chain=specs,
            config=TaskConfig(required_tier="T0", recommended_tier="T0"),
            difficulty=Difficulty.easy,
            visibility=Visibility.public,
            trust_tier_ceiling=TrustTier.verified,
        )
    return None


def replay(
    run_dir: Path,
    scorer_chain: Any = None,
) -> list[ScorerVerdict]:
    """Re-execute deterministic scorers from trajectory.jsonl alone.

    `scorer_chain` may be a `Task`, a list of `ScorerSpec`/dicts, or None.
    Returns the list of new ScorerVerdicts. If `ab_harness.scorers.runner`
    is not importable, returns a single advisory verdict.
    """
    run_dir = Path(run_dir)
    trajectory_path = run_dir / "trajectory.jsonl"

    try:
        from ab_harness.scorers.runner import (  # type: ignore[import-not-found]
            run_scorer_chain,
        )
    except ImportError:
        return _advisory("ab_harness not installed; cannot replay scorers", run_dir)

    if run_scorer_chain is None:
        return _advisory("ab_harness.scorers.runner unavailable", run_dir)

    task = _coerce_task(scorer_chain)
    if task is None:
        return _advisory(
            "no scorer_chain supplied; provide a Task or list of ScorerSpec",
            run_dir,
        )

    verdicts = run_scorer_chain(
        task=task,
        trajectory_path=trajectory_path,
        workdir=None,
        mode="replay",
    )
    return list(verdicts)


__all__ = ["replay"]
