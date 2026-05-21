"""Inspect-AI bridge (P4.19, ADR-001).

Converts our YAML-driven benchmark tasks into Inspect-AI ``Task`` objects so
``inspect eval`` can drive them. The bridge is non-invasive: we keep our
scorer chain, runner protocol, and YAML schema unchanged; the bridge just
expresses them in Inspect's vocabulary.

Public API:

* :func:`ab_task_to_sample(task)` — one ``inspect_ai.dataset.Sample`` per
  task. The prompt is the same one our runners receive (description +
  acceptance criteria). The ``metadata`` carries the full task object so
  the wrapping scorer can reach it.
* :func:`ab_scorer_chain_inspect_scorer()` — an Inspect ``@scorer`` that
  reuses our ``run_scorer_chain`` deterministic + LLM judge pipeline
  against the agent's output and trajectory.
* :func:`make_inspect_task(task)` — composes the above into a ready
  ``inspect_ai.Task``.

Usage::

    # In a user's evaluation script
    from ab_datasets.loaders import load_task
    from ab_harness.solvers.inspect_bridge import make_inspect_task
    from inspect_ai import eval

    eval(make_inspect_task(load_task("L0_001-...yaml")))

This lets us delegate orchestration (parallelism, retries, log writing,
the inspect-ai TUI / web log viewer) to Inspect-AI while keeping our
scoring logic the single source of truth.

Not in scope:

* Wiring our existing ``BaseRunner`` adapters (claude-code CLI, mock) into
  Inspect's solver protocol. That's a v2 addition — for now the bridge
  uses Inspect's stock ``generate()`` solver, which expects an Inspect-
  configured model. ``run_scorer_chain`` runs against whatever output
  Inspect produces.
"""

from __future__ import annotations

import contextlib
import json
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ab_datasets.schemas import Task


_log = logging.getLogger(__name__)


def _build_prompt(task: Task) -> str:
    """Same composition as ``ab_harness.runners._prompt.build_prompt``.

    Inlined here to avoid coupling the bridge to runner internals.
    """
    description = (task.description or "").rstrip()
    criteria = list(task.acceptance_criteria or [])
    parts: list[str] = []
    if description:
        parts.append(description)
    if criteria:
        parts.append("")
        parts.append("Acceptance criteria:")
        for i, line in enumerate(criteria, start=1):
            parts.append(f"{i}. {line}")
    return "\n".join(parts).strip() + ("\n" if parts else "")


def ab_task_to_sample(task: Task) -> Any:
    """Return a single ``Sample`` carrying the task spec as metadata."""
    from inspect_ai.dataset import Sample

    return Sample(
        id=task.id,
        input=_build_prompt(task),
        target=", ".join(task.acceptance_criteria or []),
        metadata={
            "task_id": task.id,
            "layer": getattr(task, "layer", None),
            "suite": getattr(task, "suite", None),
            "task_yaml_path": str(getattr(task, "_yaml_path", "")),
        },
    )


def _synthetic_trajectory(prompt: str, completion: str) -> list[dict[str, Any]]:
    """A two-event trajectory built from Inspect's prompt + completion.

    Our scorer chain expects a trajectory; Inspect generates plain text.
    This stub keeps the contract honest without inventing tool calls —
    deterministic scorers that depend on tool-call shape will return
    ``replay_unsupported``, which is the correct signal.
    """
    return [
        {
            "event": "run_start",
            "run_id": "inspect-bridge",
            "task_id": "via-inspect",
            "model": "inspect-eval",
            "harness": "inspect-bridge@1",
            "tier": "T0",
            "tier_hash": None,
            "dataset_version": "via-inspect",
            "prompt_template_hash": None,
            "started_at": "1970-01-01T00:00:00Z",
        },
        {
            "event": "turn",
            "idx": 0,
            "role": "assistant",
            "prompt_delta": prompt,
            "tool_calls": [],
            "tool_returns": [],
            "model_output": completion,
            "vault_state_diff": None,
            "tokens_in": 0,
            "tokens_out": 0,
            "latency_ms": 0,
            "cost_usd": 0.0,
        },
        {
            "event": "run_end",
            "finished_at": "1970-01-01T00:00:00Z",
            "status": "completed",
            "totals": {
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
                "score": 0.0,
            },
        },
    ]


def _write_trajectory_to_temp(events: list[dict[str, Any]]) -> Path:
    # NamedTemporaryFile is closed manually so the path survives for the
    # caller; not a context-manager candidate since we want delete=False
    # and explicit handoff of the path.
    with tempfile.NamedTemporaryFile(
        mode="w",
        suffix=".jsonl",
        delete=False,
        encoding="utf-8",
    ) as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")
        return Path(fh.name)


def ab_scorer_chain_inspect_scorer() -> Any:
    """Return an Inspect ``@scorer`` that runs our scorer chain.

    The wrapped chain reads Inspect's ``state.output.completion`` plus the
    sample's ``metadata.task_yaml_path`` (if present) and runs
    ``run_scorer_chain``. The verdict means are folded into an Inspect
    ``Score(value=...)``.
    """
    from ab_datasets.loaders import load_task
    from inspect_ai.scorer import Score, Target, accuracy, mean, scorer
    from inspect_ai.solver import TaskState

    from ab_harness.scorers.runner import run_scorer_chain

    @scorer(metrics=[mean(), accuracy()])
    def ab_chain_scorer():
        async def score(state: TaskState, target: Target) -> Score:
            yaml_path_str = (state.metadata or {}).get("task_yaml_path")
            if not yaml_path_str or not Path(yaml_path_str).exists():
                return Score(
                    value=0.0,
                    explanation=(
                        "task_yaml_path missing from sample metadata; "
                        "ab_task_to_sample must run before this scorer"
                    ),
                )
            task = load_task(Path(yaml_path_str))

            completion = state.output.completion or ""
            traj_events = _synthetic_trajectory(state.input_text, completion)
            traj_path = _write_trajectory_to_temp(traj_events)

            try:
                verdicts = run_scorer_chain(
                    task,
                    traj_path,
                    workdir=None,
                    mode="replay",
                )
            except Exception as exc:
                _log.exception("scorer chain raised under inspect bridge")
                return Score(value=0.0, explanation=f"scorer chain raised: {exc}")
            finally:
                with contextlib.suppress(OSError):
                    traj_path.unlink(missing_ok=True)

            if not verdicts:
                return Score(value=0.0, explanation="empty verdict list")
            scores = [float(v.score) for v in verdicts]
            mean_score = sum(scores) / len(scores)
            explanation = "; ".join(
                f"{v.scorer_name}={v.score:.2f}{'P' if v.pass_ else 'F'}"
                for v in verdicts
            )
            return Score(
                value=float(mean_score),
                explanation=explanation,
                metadata={
                    "verdicts": [
                        {
                            "scorer_name": v.scorer_name,
                            "score": float(v.score),
                            "pass": bool(v.pass_),
                        }
                        for v in verdicts
                    ]
                },
            )

        return score

    return ab_chain_scorer()


def make_inspect_task(task: Task) -> Any:
    """Compose a single-sample Inspect ``Task`` for a given AB task."""
    from inspect_ai import Task as InspectTask
    from inspect_ai.dataset import MemoryDataset
    from inspect_ai.solver import generate

    sample = ab_task_to_sample(task)
    dataset = MemoryDataset(samples=[sample], name=f"ab-{task.id}")
    return InspectTask(
        dataset=dataset,
        solver=generate(),
        scorer=ab_scorer_chain_inspect_scorer(),
        name=f"ab-{task.id}",
    )


__all__ = [
    "ab_scorer_chain_inspect_scorer",
    "ab_task_to_sample",
    "make_inspect_task",
]
