"""LLM-judge subsystem: prompt assembly + Anthropic API wrapper with VCR cache.

The scorer (`ab_harness.scorers.llm_judge_scorer`) is the public entry point;
this module owns the API + caching layer underneath.

Design constraints:

* **No live API calls in tests by default.** ``ENV AB_LLM_JUDGE_LIVE=1`` is
  required to hit Anthropic. Otherwise the judge reads from the VCR cache
  and refuses to score on a miss (returns a clear error).
* **Cache key = (model, prompt_hash)** — same prompt, same model, same
  recorded response. The cache is content-addressed under
  ``<cache_dir>/<hash>.json``.
* **Replay-friendly.** When the scorer runs in ``mode="replay"``, behavior is
  identical to ``mode="run"`` because the judge call is purely a function of
  the trajectory + task spec.
"""

from __future__ import annotations

from ab_harness.judge.client import JudgeClient, JudgeError, JudgeResponse, judge_call
from ab_harness.judge.prompts import build_judge_prompt, default_rubric

__all__ = [
    "JudgeClient",
    "JudgeError",
    "JudgeResponse",
    "build_judge_prompt",
    "default_rubric",
    "judge_call",
]
