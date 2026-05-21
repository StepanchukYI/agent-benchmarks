"""Tests for the /leaderboard `summary` field (KPI block + period-over-period deltas).

Covers four scenarios per the spec:
  1. Empty DB → summary is null.
  2. Runs in current window only → all *_delta fields are null.
  3. Runs in both windows → real deltas computed.
  4. `range` param respected → switching from 7d to 30d changes the window.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import Run, TaskResult
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "summary.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    def _override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def _add_result(
    session: Session,
    *,
    model: str,
    started_at: datetime,
    score_correctness: float,
    cost_usd: float = 0.02,
    suite: str = "L0_smoke",
    tier: str = "T0",
) -> None:
    run = Run(
        suite=suite,
        model=model,
        tier=tier,
        tier_hash="sha256:abc",
        dataset_version="0.1.0",
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=5),
        status="completed",
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    tr = TaskResult(
        task_id="L0_001",
        suite=suite,
        model=model,
        tier=tier,
        tier_hash="sha256:abc",
        status="completed",
        score_correctness=score_correctness,
        score_context_eff=0.5,
        score_tool_skill=0.5,
        score_memory=0.5,
        score_latency=0.5,
        score_total=score_correctness,
        cost_usd=cost_usd,
        latency_ms=1000,
        run_id=run.id,
    )
    session.add(tr)
    session.commit()


def test_empty_db_summary_is_null(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "summary" in body
    assert body["summary"] is None


def test_current_window_only_all_deltas_null(db_engine: object) -> None:
    now = datetime.now(UTC)
    # Only current 7d window has data — nothing in prev (7d..14d ago).
    with Session(db_engine) as session:
        _add_result(
            session,
            model="claude-sonnet-4-5",
            started_at=now - timedelta(days=1),
            score_correctness=0.80,
            cost_usd=0.02,
        )
        _add_result(
            session,
            model="claude-haiku-4-5",
            started_at=now - timedelta(days=2),
            score_correctness=0.60,
            cost_usd=0.01,
        )

    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard?range=7d")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    summary = body["summary"]
    assert summary is not None
    # Current-window aggregates present.
    assert summary["mean_correctness"] == pytest.approx(0.70, rel=1e-6)
    assert summary["runs_count_window"] == 2
    # Best correctness is the sonnet model at 0.80.
    assert summary["best_correctness_model"] == "claude-sonnet-4-5"
    assert summary["best_correctness_value"] == pytest.approx(0.80, rel=1e-6)
    # Best cost efficiency = lowest cost/correctness. haiku: 0.01/0.60; sonnet: 0.02/0.80.
    # haiku ≈ 0.01666; sonnet = 0.025 → haiku wins.
    assert summary["best_cost_efficiency_model"] == "claude-haiku-4-5"
    assert summary["best_cost_efficiency_value_usd"] == pytest.approx(
        0.01 / 0.60, rel=1e-6
    )
    # All deltas null because prev window is empty.
    assert summary["mean_correctness_delta"] is None
    assert summary["runs_count_delta"] is None
    assert summary["best_correctness_delta"] is None
    assert summary["best_cost_efficiency_delta"] is None


def test_runs_in_both_windows_real_deltas(db_engine: object) -> None:
    now = datetime.now(UTC)
    with Session(db_engine) as session:
        # Current 7d window: sonnet @ 0.80, cost 0.02 (1 run).
        _add_result(
            session,
            model="claude-sonnet-4-5",
            started_at=now - timedelta(days=2),
            score_correctness=0.80,
            cost_usd=0.02,
        )
        # Prev window (7d..14d ago): sonnet @ 0.60, cost 0.04 (1 run).
        _add_result(
            session,
            model="claude-sonnet-4-5",
            started_at=now - timedelta(days=10),
            score_correctness=0.60,
            cost_usd=0.04,
        )

    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard?range=7d")
    assert resp.status_code == 200, resp.text
    summary = resp.json()["summary"]
    assert summary is not None
    assert summary["mean_correctness"] == pytest.approx(0.80, rel=1e-6)
    assert summary["runs_count_window"] == 1
    assert summary["mean_correctness_delta"] == pytest.approx(0.20, rel=1e-6)
    assert summary["runs_count_delta"] == 0  # 1 - 1
    assert summary["best_correctness_model"] == "claude-sonnet-4-5"
    assert summary["best_correctness_delta"] == pytest.approx(0.20, rel=1e-6)
    # cost efficiency: cur = 0.02/0.80 = 0.025; prev = 0.04/0.60 ≈ 0.0667.
    # Delta = cur - prev ≈ -0.0417 (lower is better, so a negative delta = improvement).
    assert summary["best_cost_efficiency_model"] == "claude-sonnet-4-5"
    expected_delta = (0.02 / 0.80) - (0.04 / 0.60)
    assert summary["best_cost_efficiency_delta"] == pytest.approx(
        expected_delta, rel=1e-6
    )


def test_range_param_respected(db_engine: object) -> None:
    now = datetime.now(UTC)
    with Session(db_engine) as session:
        # 5 days ago — inside 7d, inside 30d.
        _add_result(
            session,
            model="m1",
            started_at=now - timedelta(days=5),
            score_correctness=0.90,
        )
        # 20 days ago — outside 7d, inside 30d.
        _add_result(
            session,
            model="m1",
            started_at=now - timedelta(days=20),
            score_correctness=0.30,
        )

    client = TestClient(app)
    body_7d = client.get("/api/v1/leaderboard?range=7d").json()
    body_30d = client.get("/api/v1/leaderboard?range=30d").json()

    summary_7d = body_7d["summary"]
    summary_30d = body_30d["summary"]
    assert summary_7d is not None
    assert summary_30d is not None
    # 7d window sees only the 0.90 row.
    assert summary_7d["runs_count_window"] == 1
    assert summary_7d["mean_correctness"] == pytest.approx(0.90, rel=1e-6)
    # 30d window sees both rows.
    assert summary_30d["runs_count_window"] == 2
    assert summary_30d["mean_correctness"] == pytest.approx(0.60, rel=1e-6)
