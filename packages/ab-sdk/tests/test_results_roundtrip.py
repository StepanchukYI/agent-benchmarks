"""Round-trip: build minimal Trajectory, write, read, validate."""

from __future__ import annotations

from datetime import UTC, datetime

from ab_datasets.schemas import Tier, Totals, Trajectory
from ab_sdk import read_run_dir, validate, write_run_dir


def test_results_roundtrip(tmp_path):
    now = datetime.now(UTC)
    trajectory = Trajectory(
        run_id="run-001",
        task_id="L0_001",
        model="x",
        harness="claude-code-cli@0.4.1",
        tier=Tier.T0,
        dataset_version="ab-datasets==0.0.1",
        started_at=now,
        finished_at=now,
        turns=[],
        status="completed",
        totals=Totals(
            tokens_in=0,
            tokens_out=0,
            latency_ms=0,
            cost_usd=0.0,
            score=0.0,
        ),
    )

    write_run_dir(
        tmp_path,
        trajectory,
        {"model": "x", "tier": "T0", "dataset_version": "0.0.1"},
    )

    run_dir = read_run_dir(tmp_path)
    assert run_dir.model == "x"
    assert run_dir.tier == "T0"
    assert run_dir.run_id == "run-001"
    assert run_dir.task_id == "L0_001"

    assert validate(tmp_path) == []
