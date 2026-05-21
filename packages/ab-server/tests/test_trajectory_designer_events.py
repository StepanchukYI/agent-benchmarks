"""Designer's TurnEvent shape: kind ∈ {prompt,tool,read,write,thought,judge,verdict} + lucide icon."""

from __future__ import annotations

import json
from pathlib import Path

from ab_server.api._trajectory_view import assemble_trajectory_view


def _write_events(path: Path, events: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


def test_events_classify_prompt_write_thought_judge_verdict(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_events(
        traj,
        [
            {
                "event": "run_start",
                "run_id": "r1",
                "task_id": "L0_001",
                "model": "claude-sonnet-4-5",
                "harness": "claude-code-cli@unknown",
                "tier": "T0",
                "dataset_version": "0.0.1",
                "started_at": "2026-05-21T00:00:00Z",
            },
            {
                "event": "turn",
                "idx": 0,
                "role": "user",
                "model_output": "Create notes/greeting.txt with 'Hello'.",
                "tool_calls": [],
                "tool_returns": [],
                "tokens_in": 100,
                "tokens_out": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
            },
            {
                "event": "turn",
                "idx": 1,
                "role": "assistant",
                "model_output": "I'll create the file.",
                "tool_calls": [{"name": "Write", "args": {"path": "notes/greeting.txt"}}],
                "tool_returns": [],
                "tokens_in": 200,
                "tokens_out": 80,
                "latency_ms": 1500,
                "cost_usd": 0.01,
            },
            {
                "event": "turn",
                "idx": 2,
                "role": "tool",
                "model_output": "",
                "tool_calls": [],
                "tool_returns": [{"path": "notes/greeting.txt", "content": "Hello"}],
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": 5,
                "cost_usd": 0.0,
            },
            {
                "event": "turn",
                "idx": 3,
                "role": "assistant",
                "model_output": "Done.",
                "tool_calls": [],
                "tool_returns": [],
                "tokens_in": 50,
                "tokens_out": 5,
                "latency_ms": 300,
                "cost_usd": 0.001,
            },
            {
                "event": "scorer",
                "scorer_name": "file_diff",
                "kind": "deterministic",
                "pass": True,
                "score": 1.0,
                "detail": {"ok": True},
            },
            {
                "event": "scorer",
                "scorer_name": "hallucination_check",
                "kind": "llm_judge",
                "pass": True,
                "score": 0.92,
                "detail": {"ensemble": 3},
            },
            {
                "event": "run_end",
                "finished_at": "2026-05-21T00:00:14Z",
                "status": "completed",
                "totals": {"tokens_in": 350, "tokens_out": 85, "latency_ms": 1805, "cost_usd": 0.011, "score": 0.96},
            },
        ],
    )

    view = assemble_trajectory_view(traj)
    assert "events" in view
    events = view["events"]
    assert [e["kind"] for e in events] == ["prompt", "write", "tool", "thought", "verdict", "judge"]
    assert [e["icon"] for e in events] == [
        "user",
        "pencil",
        "cube",
        "brain",
        "check-circle-2",
        "scale",
    ]
    write_event = events[1]
    assert "notes/greeting.txt" in write_event["label"]
    judge_event = events[5]
    assert "score 0.92" in judge_event["meta"]


def test_read_tool_classified_as_read(tmp_path: Path) -> None:
    traj = tmp_path / "trajectory.jsonl"
    _write_events(
        traj,
        [
            {
                "event": "run_start",
                "run_id": "r1",
                "task_id": "L0_001",
                "model": "claude-sonnet-4-5",
                "harness": "claude-code-cli@unknown",
                "tier": "T0",
                "dataset_version": "0.0.1",
                "started_at": "2026-05-21T00:00:00Z",
            },
            {
                "event": "turn",
                "idx": 0,
                "role": "assistant",
                "model_output": "",
                "tool_calls": [{"name": "Read", "args": {"path": "source.py"}}],
                "tool_returns": [],
                "tokens_in": 100,
                "tokens_out": 30,
                "latency_ms": 200,
                "cost_usd": 0.002,
            },
            {
                "event": "run_end",
                "finished_at": "2026-05-21T00:00:01Z",
                "status": "completed",
                "totals": {"tokens_in": 100, "tokens_out": 30, "latency_ms": 200, "cost_usd": 0.002, "score": 0.0},
            },
        ],
    )
    view = assemble_trajectory_view(traj)
    assert view["events"][0]["kind"] == "read"
    assert view["events"][0]["icon"] == "file-text"


def test_events_preserve_order_with_interleaved_scorers(tmp_path: Path) -> None:
    """Designer's timeline expects events in JSONL order (turns then scorers)."""
    traj = tmp_path / "trajectory.jsonl"
    _write_events(
        traj,
        [
            {
                "event": "run_start",
                "run_id": "r1",
                "task_id": "L0_001",
                "model": "m",
                "harness": "h",
                "tier": "T0",
                "dataset_version": "0.0.1",
                "started_at": "2026-05-21T00:00:00Z",
            },
            {
                "event": "turn",
                "idx": 0,
                "role": "assistant",
                "model_output": "hi",
                "tool_calls": [],
                "tool_returns": [],
                "tokens_in": 1,
                "tokens_out": 1,
                "latency_ms": 1,
                "cost_usd": 0.0,
            },
            {
                "event": "scorer",
                "scorer_name": "exec",
                "kind": "exec",
                "pass": True,
                "score": 1.0,
                "detail": {},
            },
            {
                "event": "run_end",
                "finished_at": "2026-05-21T00:00:01Z",
                "status": "completed",
                "totals": {"tokens_in": 1, "tokens_out": 1, "latency_ms": 1, "cost_usd": 0.0, "score": 1.0},
            },
        ],
    )
    view = assemble_trajectory_view(traj)
    assert len(view["events"]) == 2
    assert view["events"][0]["kind"] == "thought"
    assert view["events"][1]["kind"] == "verdict"
