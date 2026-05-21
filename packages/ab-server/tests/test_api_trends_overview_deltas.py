"""Tests for the new 30-day delta fields on /trends/overview.

active_regressions_delta_30d / improvements_delta_30d are computed by
comparing the current 30d window (counted via compute_regressions
arithmetic) against the prior 30d window (now-60d → now-30d compared to
now-90d → now-60d). When the prior window has no data at all, both
deltas are null.
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
    db_path = tmp_path / "overview.db"
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


def _add(
    session: Session,
    *,
    model: str,
    tier: str,
    suite: str,
    started_at: datetime,
    score_total: float,
) -> None:
    run = Run(
        suite=suite,
        model=model,
        tier=tier,
        tier_hash="sha256:abc",
        dataset_version="0.1.0",
        started_at=started_at,
        finished_at=started_at + timedelta(minutes=1),
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
        score_total=score_total,
        cost_usd=0.01,
        latency_ms=100,
        run_id=run.id,
    )
    session.add(tr)
    session.commit()


def test_empty_db_deltas_null(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/trends/overview")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "active_regressions_delta_30d" in body
    assert "improvements_delta_30d" in body
    assert body["active_regressions_delta_30d"] is None
    assert body["improvements_delta_30d"] is None
    # Backward-compat: existing fields still present.
    assert body["active_regressions_count"] == 0
    assert body["improvements_count"] == 0


def test_only_recent_data_prior_window_empty_deltas_null(
    db_engine: object,
) -> None:
    """Data only in current 30d → prior window is empty → deltas null."""
    now = datetime.now(UTC)
    with Session(db_engine) as session:
        for day in range(14):
            score = 0.70 if day < 7 else 0.80
            _add(
                session,
                model="claude-sonnet-4-5",
                tier="T2",
                suite="L0_smoke",
                started_at=now - timedelta(days=day, hours=1),
                score_total=score,
            )

    client = TestClient(app)
    resp = client.get("/api/v1/trends/overview")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["active_regressions_delta_30d"] is None
    assert body["improvements_delta_30d"] is None


def test_data_in_both_30d_windows_real_deltas(db_engine: object) -> None:
    """Seed data in both [now-30d, now) and [now-90d, now-30d) windows.

    Construct a regression in BOTH the current 30d window and the prior
    30d window so the delta is a real integer (not null).
    """
    now = datetime.now(UTC)
    with Session(db_engine) as session:
        # Current 30d block: high scores [0..15d], low scores [15..30d) → regression.
        for day in range(30):
            score = 0.80 if day < 15 else 0.50
            _add(
                session,
                model="m_current",
                tier="T0",
                suite="L0_smoke",
                started_at=now - timedelta(days=day, hours=1),
                score_total=score,
            )
        # Prior 30d block: high [30..45d], low [45..60d) → another regression.
        for day in range(30, 60):
            # `current` half of prior window is [30..45d]; `prev` half is [45..60d].
            # In compute_regressions arithmetic anchored at now-30d:
            #   prev_now = now - 30d
            #   current bucket = [prev_now - 30d, prev_now) = [-60d, -30d)
            #   prev bucket = [prev_now - 60d, prev_now - 30d) = [-90d, -60d)
            # so within the prior window's "current half" (30..60d ago), we
            # want a regression. Mirror the current-window shape.
            score = 0.80 if day < 45 else 0.50
            _add(
                session,
                model="m_prior",
                tier="T0",
                suite="L0_smoke",
                started_at=now - timedelta(days=day, hours=1),
                score_total=score,
            )
        # And data in [60..90d] to give the prior window's "prev half" content.
        for day in range(60, 90):
            _add(
                session,
                model="m_prior",
                tier="T0",
                suite="L0_smoke",
                started_at=now - timedelta(days=day, hours=1),
                score_total=0.80,
            )

    client = TestClient(app)
    resp = client.get("/api/v1/trends/overview")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Both should be integers when prior window has data.
    assert isinstance(body["active_regressions_delta_30d"], int)
    assert isinstance(body["improvements_delta_30d"], int)
