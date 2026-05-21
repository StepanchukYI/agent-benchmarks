from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from ab_server.api._trajectory_view import (
    _CONTENT_CAP_BYTES,
    assemble_trajectory_view,
)
from ab_server.models import RegisteredRepo, Submission, TaskResult


def _write_trajectory(path: Path, events: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def _events_basic() -> list[dict]:
    return [
        {
            "event": "run_start",
            "run_id": "r1",
            "task_id": "L0_001",
            "model": "claude-sonnet",
            "harness": "claude-code-cli@0.4.1",
            "tier": "T0",
            "tier_hash": "sha256:0",
            "dataset_version": "ab-datasets==0.0.1",
            "started_at": "2026-05-21T12:00:00Z",
        },
        {
            "event": "turn",
            "idx": 0,
            "role": "assistant",
            "tool_calls": [
                {
                    "name": "write_file",
                    "args": {"path": "notes/greeting.txt", "content": "Hello, Example.\n"},
                }
            ],
            "tool_returns": [{"path": "notes/greeting.txt", "content": "Hello, Example.\n"}],
            "model_output": "wrote file",
            "vault_state_diff": {"created": ["notes/greeting.txt"], "modified": [], "deleted": []},
            "tokens_in": 12,
            "tokens_out": 6,
            "latency_ms": 100,
            "cost_usd": 0.0,
        },
        {
            "event": "scorer",
            "scorer_name": "file_diff",
            "kind": "deterministic",
            "pass": True,
            "score": 1.0,
            "detail": {"diff": []},
        },
        {
            "event": "run_end",
            "finished_at": "2026-05-21T12:00:14Z",
            "status": "completed",
            "totals": {"tokens_in": 12, "tokens_out": 6, "latency_ms": 100, "cost_usd": 0.0, "score": 1.0},
        },
    ]


def test_assemble_basic_shape(tmp_path: Path) -> None:
    traj_path = tmp_path / "trajectory.jsonl"
    _write_trajectory(traj_path, _events_basic())

    view = assemble_trajectory_view(traj_path)

    assert view["header"]["run_id"] == "r1"
    assert view["header"]["task_id"] == "L0_001"
    assert view["header"]["status"] == "completed"
    assert view["header"]["totals"]["score"] == 1.0

    assert len(view["turns"]) == 1
    turn = view["turns"][0]
    assert turn["idx"] == 0
    assert turn["role"] == "assistant"
    assert turn["model_output"] == "wrote file"
    assert len(turn["tool_calls"]) == 1
    assert turn["tool_calls"][0]["name"] == "write_file"
    assert turn["tool_calls"][0]["args"]["path"] == "notes/greeting.txt"
    assert turn["tool_calls"][0]["truncated"] is False
    assert len(turn["tool_returns"]) == 1
    assert turn["tool_returns"][0]["path"] == "notes/greeting.txt"
    assert turn["truncated"] is False

    assert len(view["scorers"]) == 1
    assert view["scorers"][0]["scorer_name"] == "file_diff"
    assert view["scorers"][0]["pass"] is True

    assert view["trust"]["tier"] == "self_reported"
    assert view["pillars"] is None


def test_assemble_truncates_large_tool_call(tmp_path: Path) -> None:
    events = _events_basic()
    big_content = "x" * (_CONTENT_CAP_BYTES + 10)
    events[1]["tool_calls"][0]["args"] = {"content": big_content}
    events[1]["tool_returns"][0]["content"] = big_content
    events[1]["model_output"] = "x" * (_CONTENT_CAP_BYTES + 100)

    traj_path = tmp_path / "trajectory.jsonl"
    _write_trajectory(traj_path, events)

    view = assemble_trajectory_view(traj_path)
    turn = view["turns"][0]
    assert turn["truncated"] is True
    assert turn["tool_calls"][0]["truncated"] is True
    assert turn["tool_returns"][0]["truncated"] is True


def test_assemble_with_submission_and_task_result(tmp_path: Path) -> None:
    traj_path = tmp_path / "trajectory.jsonl"
    _write_trajectory(traj_path, _events_basic())

    repo = RegisteredRepo(
        id=uuid4(),
        user_id=uuid4(),
        repo_url="https://github.com/alice/results",
        default_branch="main",
    )
    submission = Submission(
        registered_repo_id=repo.id,
        source_commit_sha="sha-abc",
        source_path="results/run-1",
        trust_tier="verified",
        re_scored_at=datetime(2026, 5, 21, tzinfo=UTC),
        discrepancy_pct=0.001,
        model="claude-sonnet",
        tier="T0",
        dataset_version="ab-datasets==0.0.1",
    )
    task_result = TaskResult(
        submission_id=submission.id,
        task_id="L0_001",
        suite="file-ops",
        model="claude-sonnet",
        tier="T0",
        tier_hash="sha256:0",
        status="completed",
        score_correctness=0.9,
        score_context_eff=0.8,
        score_tool_skill=0.7,
        score_memory=0.6,
        score_latency=0.5,
        score_total=0.8,
    )
    view = assemble_trajectory_view(
        traj_path, submission=submission, task_result=task_result, repo=repo
    )
    assert view["trust"]["tier"] == "verified"
    assert view["trust"]["source_commit_sha"] == "sha-abc"
    assert view["trust"]["source_path"] == "results/run-1"
    assert view["trust"]["repo_url"] == "https://github.com/alice/results"
    assert view["trust"]["re_scored_at"] is not None
    assert view["pillars"]["correctness"] == 0.9
    assert view["pillars"]["latency"] == 0.5
