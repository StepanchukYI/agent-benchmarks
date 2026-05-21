"""LLM-judge scorer (P2.11).

Real implementation. Calls a small judge model (default ``claude-haiku-4-5``)
with a rubric prompt + summarised trajectory, parses the JSON score, returns
a verdict.

LSN-004 (CLAUDE.md): the chain runner does NOT enforce "always pair LLM-judge
with a deterministic scorer" — that's a task-authoring contract. The scorer
here is well-behaved when paired; on its own it's a single signal source and
should NOT be the only verdict in a chain.

Config (from task YAML, all optional):

* ``judge_model: str`` — default ``"claude-haiku-4-5"``.
* ``rubric: str`` — overrides the default rubric prompt.
* ``cache_dir: str`` — directory for VCR fixtures. Default
  ``tests/fixtures/llm_judge`` relative to the repo root if discoverable,
  else ``~/.cache/agent-benchmarks/llm-judge``.
* ``n_judges: int`` — ensemble size. Default 1. Higher values send the same
  prompt N times and average the scores. Each call still uses the same
  cache key (so N>1 in cache-only mode is the same as N=1).
* ``allow_live: bool | None`` — override the ``AB_LLM_JUDGE_LIVE`` env.
  Tests pass ``False`` to be paranoid; default ``None`` consults the env.

Replay support: identical to run mode, since the judge prompt is purely
a function of trajectory + task spec. The trajectory_path is read; the
workdir is not consulted.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.judge import build_judge_prompt, judge_call
from ab_harness.judge.client import JudgeError
from ab_harness.judge.prompts import summarize_trajectory_for_judge
from ab_harness.scorers._base import score_to_verdict

_log = logging.getLogger(__name__)

_DEFAULT_MODEL = "claude-haiku-4-5"


def _discover_cache_dir(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit)
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "tests" / "fixtures" / "llm_judge"
        if candidate.parent.exists():
            return candidate
    return Path.home() / ".cache" / "agent-benchmarks" / "llm-judge"


def _load_trajectory_events(trajectory_path: Path | None) -> list[dict[str, Any]]:
    if trajectory_path is None or not trajectory_path.exists():
        return []
    events: list[dict[str, Any]] = []
    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                events.append(json.loads(stripped))
            except json.JSONDecodeError:
                continue
    return events


def llm_judge_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    **scorer_config: Any,
) -> ScorerVerdict:
    name = str(scorer_config.get("scorer_name") or "llm_judge")
    judge_model = str(scorer_config.get("judge_model") or _DEFAULT_MODEL)
    rubric = scorer_config.get("rubric")
    n_judges = max(1, int(scorer_config.get("n_judges") or 1))
    cache_dir = _discover_cache_dir(scorer_config.get("cache_dir"))
    allow_live = scorer_config.get("allow_live")

    if task is None:
        return score_to_verdict(
            name,
            ScorerKind.llm_judge,
            ok=False,
            score=0.0,
            detail={"error": "task required for llm_judge", "mode": mode},
        )

    events = _load_trajectory_events(trajectory_path)
    if not events:
        return score_to_verdict(
            name,
            ScorerKind.llm_judge,
            ok=False,
            score=0.0,
            detail={
                "error": "no trajectory events to judge",
                "trajectory_path": str(trajectory_path) if trajectory_path else None,
                "mode": mode,
            },
        )

    trajectory_summary = summarize_trajectory_for_judge(events)
    prompt = build_judge_prompt(task, trajectory_summary, rubric=rubric)

    scores: list[float] = []
    passes: list[bool] = []
    reasonings: list[str] = []
    cached_flags: list[bool] = []

    for i in range(n_judges):
        try:
            resp = judge_call(
                model=judge_model,
                prompt=prompt,
                cache_dir=cache_dir,
                allow_live=allow_live,
            )
        except JudgeError as exc:
            return score_to_verdict(
                name,
                ScorerKind.llm_judge,
                ok=False,
                score=0.0,
                detail={
                    "error": str(exc),
                    "judge_model": judge_model,
                    "iteration": i,
                    "live_env": os.environ.get("AB_LLM_JUDGE_LIVE"),
                },
            )
        scores.append(resp.score)
        passes.append(resp.pass_)
        reasonings.append(resp.reasoning)
        cached_flags.append(resp.cached)

    mean_score = sum(scores) / len(scores)
    # Ensemble pass: majority vote, with score>=0.5 as the tiebreaker.
    pass_votes = sum(1 for p in passes if p)
    overall_pass = pass_votes > n_judges // 2 or (
        pass_votes == n_judges // 2 and mean_score >= 0.5
    )

    return score_to_verdict(
        name,
        ScorerKind.llm_judge,
        ok=overall_pass,
        score=float(mean_score),
        detail={
            "judge_model": judge_model,
            "n_judges": n_judges,
            "scores": scores,
            "mean_score": float(mean_score),
            "pass_votes": pass_votes,
            "reasonings": reasonings,
            "all_cached": all(cached_flags),
            "any_live": any(not c for c in cached_flags),
            "mode": mode,
        },
    )
