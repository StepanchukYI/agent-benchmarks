from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import (
    Difficulty,
    Layer,
    ScorerKind,
    ScorerSpec,
    Task,
    TaskConfig,
)
from ab_harness.scorers.runner import run_scorer_chain


def _task_with_chain() -> Task:
    return Task(
        id="L0_runner",
        layer=Layer.L0,
        suite="runner",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
        scorer_chain=[
            ScorerSpec(
                name="file_diff",
                kind=ScorerKind.deterministic,
                config={"expected": {"out.txt": "hi\n"}},
            ),
            ScorerSpec(
                name="schema",
                kind=ScorerKind.schema,
                config={
                    "target": "data.json",
                    "schema": {
                        "type": "object",
                        "properties": {"x": {"type": "integer"}},
                        "required": ["x"],
                    },
                },
            ),
            ScorerSpec(
                name="privacy_check",
                kind=ScorerKind.privacy_check,
                config={},
            ),
        ],
    )


def test_runner_three_scorers_in_order(tmp_path: Path) -> None:
    (tmp_path / "out.txt").write_text("hi\n", encoding="utf-8")
    (tmp_path / "data.json").write_text(json.dumps({"x": 1}), encoding="utf-8")

    traj = tmp_path / "trajectory.jsonl"
    traj.write_text(
        "\n".join(
            json.dumps(e)
            for e in [
                {"event": "run_start", "run_id": "r", "task_id": "L0_runner"},
                {
                    "event": "turn",
                    "idx": 0,
                    "role": "assistant",
                    "tool_calls": [],
                    "tool_returns": [],
                    "model_output": "clean",
                    "vault_state_diff": None,
                },
                {"event": "run_end", "status": "completed"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    verdicts = run_scorer_chain(
        task=_task_with_chain(),
        trajectory_path=traj,
        workdir=tmp_path,
        mode="run",
    )

    assert len(verdicts) == 3
    assert verdicts[0].scorer_name == "file_diff"
    assert verdicts[1].scorer_name == "schema"
    assert verdicts[2].scorer_name == "privacy_check"
    assert all(v.pass_ for v in verdicts)


def test_runner_unknown_scorer_records_error(tmp_path: Path) -> None:
    task = Task(
        id="L0_runner_err",
        layer=Layer.L0,
        suite="runner",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
        scorer_chain=[
            ScorerSpec(
                name="nonexistent",
                kind=ScorerKind.deterministic,
                config={},
            )
        ],
    )
    verdicts = run_scorer_chain(task=task, workdir=tmp_path, mode="run")
    assert len(verdicts) == 1
    assert verdicts[0].pass_ is False
    assert isinstance(verdicts[0].detail, dict)
    assert "error" in verdicts[0].detail


def test_runner_replay_mode_no_workdir(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    traj.write_text(
        "\n".join(
            json.dumps(e)
            for e in [
                {"event": "run_start", "run_id": "r", "task_id": "L0_runner"},
                {
                    "event": "turn",
                    "idx": 0,
                    "role": "assistant",
                    "tool_calls": [],
                    "tool_returns": [],
                    "model_output": "ok",
                    "vault_state_diff": None,
                },
                {"event": "run_end", "status": "completed"},
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    task = Task(
        id="L0_replay",
        layer=Layer.L0,
        suite="runner",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
        scorer_chain=[
            ScorerSpec(name="privacy_check", kind=ScorerKind.privacy_check, config={}),
        ],
    )
    verdicts = run_scorer_chain(task=task, trajectory_path=traj, mode="replay")
    assert len(verdicts) == 1
    assert verdicts[0].pass_ is True
