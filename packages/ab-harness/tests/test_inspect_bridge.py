"""Inspect-AI bridge — sample construction + task composition + scorer adapter.

Validates the bridge structure without running a full ``inspect eval`` (which
needs a real model). The scorer's async logic is exercised separately by
calling the inner coroutine directly with a stub TaskState.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from ab_harness.solvers.inspect_bridge import (
    _build_prompt,
    _synthetic_trajectory,
    ab_scorer_chain_inspect_scorer,
    ab_task_to_sample,
    make_inspect_task,
)


def _fake_task(**overrides: Any) -> Any:
    base = SimpleNamespace(
        id="L0_001",
        description="Create notes/greeting.txt with `Hello, Example.\\n`.",
        acceptance_criteria=[
            "File exists",
            "Bytes match exactly",
        ],
        layer="L0",
        suite="L0_smoke",
    )
    for k, v in overrides.items():
        setattr(base, k, v)
    return base


# ---------------------------------------------------------------------------
# Prompt + sample
# ---------------------------------------------------------------------------


def test_build_prompt_emits_description_and_criteria() -> None:
    task = _fake_task()
    prompt = _build_prompt(task)
    assert task.description.strip() in prompt
    assert "Acceptance criteria:" in prompt
    assert "1. File exists" in prompt
    assert "2. Bytes match exactly" in prompt


def test_build_prompt_no_criteria() -> None:
    task = _fake_task(acceptance_criteria=[])
    prompt = _build_prompt(task)
    assert "Acceptance criteria:" not in prompt
    assert task.description.strip() in prompt


def test_ab_task_to_sample_carries_metadata() -> None:
    task = _fake_task()
    task._yaml_path = "/tmp/path/L0_001.yaml"
    sample = ab_task_to_sample(task)
    assert sample.id == "L0_001"
    assert "notes/greeting.txt" in sample.input
    assert sample.metadata["task_id"] == "L0_001"
    assert sample.metadata["suite"] == "L0_smoke"
    assert sample.metadata["task_yaml_path"] == "/tmp/path/L0_001.yaml"


# ---------------------------------------------------------------------------
# Synthetic trajectory shape
# ---------------------------------------------------------------------------


def test_synthetic_trajectory_has_run_start_turn_run_end() -> None:
    events = _synthetic_trajectory("PROMPT", "COMPLETION")
    types = [e["event"] for e in events]
    assert types == ["run_start", "turn", "run_end"]
    assert events[1]["model_output"] == "COMPLETION"
    assert events[1]["prompt_delta"] == "PROMPT"
    assert events[1]["tool_calls"] == []


# ---------------------------------------------------------------------------
# Scorer adapter — exercises run_scorer_chain via a real L0_001 task on disk
# ---------------------------------------------------------------------------


def _real_l0_001_task() -> Any:
    """Load the actual L0_001 task YAML if it ships with this checkout."""
    from ab_datasets.loaders import load_task

    candidates = [
        Path(__file__).resolve().parents[2]
        / "packages"
        / "ab-datasets"
        / "ab_datasets"
        / "L0_foundation",
        Path(__file__).resolve().parents[3]
        / "packages"
        / "ab-datasets"
        / "ab_datasets"
        / "L0_foundation",
    ]
    for root in candidates:
        if not root.exists():
            continue
        for yml in root.glob("L0_001-*.yaml"):
            return load_task(yml), yml
    pytest.skip("L0_001 task YAML not in checkout")


def test_scorer_returns_low_score_when_yaml_missing(tmp_path: Path) -> None:
    """If sample metadata lacks task_yaml_path, the scorer must not crash."""
    from inspect_ai.scorer import Target

    scorer_obj = ab_scorer_chain_inspect_scorer()
    state = _make_task_state(
        completion="anything",
        metadata={},  # missing task_yaml_path
    )
    score = asyncio.get_event_loop().run_until_complete(
        scorer_obj(state, Target("ignored"))
    )
    assert float(score.value) == 0.0
    assert "task_yaml_path" in (score.explanation or "")


def test_scorer_runs_chain_against_real_task() -> None:
    task_yml = _real_l0_001_task()
    if task_yml is None:
        return
    _, yaml_path = task_yml

    from inspect_ai.scorer import Target

    scorer_obj = ab_scorer_chain_inspect_scorer()
    state = _make_task_state(
        completion="(synthetic — agent did nothing)",
        metadata={"task_yaml_path": str(yaml_path), "task_id": "L0_001"},
    )
    score = asyncio.get_event_loop().run_until_complete(
        scorer_obj(state, Target("ignored"))
    )
    # No tool calls in the synthetic trajectory → file_diff replay fails;
    # privacy_check passes; total stays low.
    assert 0.0 <= float(score.value) <= 1.0
    md = score.metadata or {}
    # We don't pin verdict count — depends on the YAML's scorer_chain — but
    # there must be at least one verdict object.
    assert "verdicts" in md
    assert len(md["verdicts"]) >= 1


# ---------------------------------------------------------------------------
# make_inspect_task composition
# ---------------------------------------------------------------------------


def test_make_inspect_task_composes_dataset_solver_scorer(tmp_path: Path) -> None:
    task = _fake_task()
    task._yaml_path = str(tmp_path / "fake.yaml")
    insp = make_inspect_task(task)
    # Inspect's Task carries a dataset, solver, scorer trio. We don't run it,
    # just confirm wiring.
    assert insp.name == "ab-L0_001"
    samples = list(insp.dataset.samples) if hasattr(insp.dataset, "samples") else list(insp.dataset)
    assert len(samples) == 1
    assert samples[0].id == "L0_001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task_state(*, completion: str, metadata: dict[str, Any]) -> Any:
    """Build the minimum TaskState the scorer reads from."""
    from inspect_ai.model import ModelOutput
    from inspect_ai.solver import TaskState

    output = ModelOutput.from_content(model="stub", content=completion)
    return TaskState(
        model="stub",
        sample_id="L0_001",
        epoch=0,
        input="PROMPT",
        messages=[],
        output=output,
        completed=True,
        metadata=metadata,
    )
