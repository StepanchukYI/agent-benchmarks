"""LLM-judge rubric prompts.

The judge prompt is built from four parts:

1. **System rubric** — tells the model what scoring scale + format to use.
2. **Task spec** — id, description, acceptance criteria.
3. **Trajectory summary** — turn count, tool calls, model output snippets,
   final workdir diff. We do NOT dump the full raw trajectory — judges
   waste context budget on tool noise. The summary keeps the signal.
4. **Output schema** — JSON object the judge must emit, parsed by the
   scorer. Validated against a strict shape.

The default rubric is intentionally generic — task-specific rubrics override
via ``scorer.config.rubric``.
"""

from __future__ import annotations

import json
from typing import Any

from ab_datasets.schemas import Task

DEFAULT_RUBRIC: str = (
    "You are an impartial benchmark judge. Given a task spec and an agent's "
    "trajectory + final output, score how well the agent accomplished the "
    "task on a 0.0-1.0 scale:\n"
    "  0.0 = complete miss (wrong artifact, refused, off-task)\n"
    "  0.5 = partial credit (right shape, missing details OR right idea "
    "but bugs)\n"
    "  1.0 = perfect (matches every acceptance criterion verbatim)\n\n"
    "Be strict but fair. Prefer partial credit over binary fail when the "
    "agent obviously tried and got most of the way. Do NOT inflate the "
    "score for effort alone."
)

OUTPUT_SCHEMA: str = (
    "Respond with a JSON object on a single line, no markdown, no prose "
    'outside the object: {"score": <float 0..1>, "reasoning": '
    '"<one-sentence justification>", "pass": <true|false>}. '
    "Set pass=true iff score >= 0.5."
)


def default_rubric() -> str:
    return DEFAULT_RUBRIC


def build_judge_prompt(
    task: Task,
    trajectory_summary: dict[str, Any],
    *,
    rubric: str | None = None,
) -> str:
    """Compose the full judge prompt from task + trajectory summary.

    ``trajectory_summary`` is the output of
    :func:`summarize_trajectory_for_judge` — keep it small so the judge
    spends its context budget on judgment, not tool noise.
    """
    rubric_text = rubric or DEFAULT_RUBRIC
    acceptance = list(getattr(task, "acceptance_criteria", []) or [])

    parts = [
        "## Rubric",
        rubric_text,
        "",
        "## Task",
        f"id: {task.id}",
        f"description: {(task.description or '').strip()}",
        "",
        "## Acceptance criteria",
    ]
    for i, line in enumerate(acceptance, start=1):
        parts.append(f"{i}. {line}")
    parts.extend(
        [
            "",
            "## Trajectory summary",
            json.dumps(trajectory_summary, indent=2, default=str, sort_keys=True),
            "",
            "## Output",
            OUTPUT_SCHEMA,
        ]
    )
    return "\n".join(parts)


def summarize_trajectory_for_judge(
    trajectory_events: list[dict[str, Any]],
    *,
    model_output_limit: int = 1200,
    tool_call_limit: int = 20,
) -> dict[str, Any]:
    """Distill a trajectory.jsonl event list into a judge-friendly summary.

    Keeps tool-call names + truncated args, dropping verbose result bodies.
    Caps model_output at ``model_output_limit`` chars to stop the judge
    from drowning in the agent's chain of thought.
    """
    tool_calls: list[dict[str, Any]] = []
    totals = {"turns": 0, "tool_calls": 0, "tokens_in": 0, "tokens_out": 0}
    final_output_parts: list[str] = []
    run_start: dict[str, Any] = {}
    run_end: dict[str, Any] = {}

    for event in trajectory_events:
        etype = event.get("event")
        if etype == "run_start":
            run_start = {
                "run_id": event.get("run_id"),
                "task_id": event.get("task_id"),
                "model": event.get("model"),
                "tier": event.get("tier"),
            }
            continue
        if etype == "run_end":
            run_end = {
                "status": event.get("status"),
                "totals": event.get("totals"),
            }
            continue
        if etype != "turn":
            continue

        totals["turns"] += 1
        totals["tokens_in"] += int(event.get("tokens_in") or 0)
        totals["tokens_out"] += int(event.get("tokens_out") or 0)

        for call in event.get("tool_calls") or []:
            totals["tool_calls"] += 1
            if len(tool_calls) < tool_call_limit:
                tool_calls.append(
                    {
                        "name": call.get("name"),
                        "args_brief": _truncate(
                            json.dumps(call.get("args", {}), default=str),
                            240,
                        ),
                    }
                )

        out = event.get("model_output") or ""
        if out:
            final_output_parts.append(out)

    final_output = "\n".join(final_output_parts)
    if len(final_output) > model_output_limit:
        final_output = (
            final_output[: model_output_limit // 2]
            + f"\n... [truncated, {len(final_output)} total chars] ...\n"
            + final_output[-model_output_limit // 2 :]
        )

    return {
        "run_start": run_start,
        "run_end": run_end,
        "totals": totals,
        "tool_calls": tool_calls,
        "tool_calls_truncated": totals["tool_calls"] > len(tool_calls),
        "final_output": final_output,
    }


def _truncate(s: str, limit: int) -> str:
    if len(s) <= limit:
        return s
    return s[:limit] + f"...[+{len(s) - limit} chars]"


__all__ = [
    "DEFAULT_RUBRIC",
    "OUTPUT_SCHEMA",
    "build_judge_prompt",
    "default_rubric",
    "summarize_trajectory_for_judge",
]
