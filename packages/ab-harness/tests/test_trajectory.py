"""Round-trip: write run_start + 2 turns + run_end, validate, reassemble."""

from __future__ import annotations

import pytest
from ab_harness.trajectory import TrajectoryReader, TrajectoryWriter, validate

pytest.importorskip("ab_datasets.schemas")


def test_trajectory_roundtrip(tmp_path):
    path = tmp_path / "trajectory.jsonl"

    with TrajectoryWriter(path) as w:
        w.write_run_start(
            {
                "run_id": "r1",
                "task_id": "L0_001",
                "model": "claude-sonnet-4-5",
                "harness": "claude-code-cli@0.4.1",
                "tier": "T0",
                "tier_hash": "sha256:abc",
                "dataset_version": "ab-datasets==0.0.1",
                "prompt_template_hash": "sha256:def",
                "started_at": "2026-05-21T12:00:00Z",
            }
        )
        w.write_turn(
            {
                "idx": 0,
                "role": "user",
                "prompt_delta": "hi",
                "tool_calls": [],
                "tool_returns": [],
                "model_output": "",
                "vault_state_diff": None,
                "tokens_in": 10,
                "tokens_out": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
            }
        )
        w.write_turn(
            {
                "idx": 1,
                "role": "assistant",
                "tool_calls": [],
                "tool_returns": [],
                "model_output": "ok",
                "vault_state_diff": None,
                "tokens_in": 5,
                "tokens_out": 3,
                "latency_ms": 10,
                "cost_usd": 0.0001,
            }
        )
        w.write_run_end(
            {
                "finished_at": "2026-05-21T12:00:14Z",
                "status": "completed",
                "totals": {
                    "tokens_in": 15,
                    "tokens_out": 3,
                    "latency_ms": 10,
                    "cost_usd": 0.0001,
                    "score": 1.0,
                },
            }
        )

    assert validate(path) == []

    traj = TrajectoryReader.to_trajectory(path)
    assert len(traj.turns) == 2
