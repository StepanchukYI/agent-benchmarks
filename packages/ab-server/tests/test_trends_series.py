from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.leaderboard import compute_trends_series
from ab_server.main import app
from ab_server.models import Run, TaskResult
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "trends.db"
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


def _seed_days(engine: object, days: int) -> None:
    with Session(engine) as session:
        now = datetime.now(UTC)
        for d in range(days):
            started = now - timedelta(days=d)
            run = Run(
                suite="L0_smoke",
                model="claude-sonnet-4-5",
                tier="T2",
                tier_hash="sha256:abc",
                dataset_version="0.1.0",
                started_at=started,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            tr = TaskResult(
                task_id="L0_001",
                suite="L0_smoke",
                model="claude-sonnet-4-5",
                tier="T2",
                tier_hash="sha256:abc",
                status="completed",
                score_total=0.5,
                cost_usd=0.01,
                latency_ms=1000,
                run_id=run.id,
            )
            session.add(tr)
        session.commit()


def test_trends_series_returns_window_array(db_engine: object) -> None:
    _seed_days(db_engine, 30)
    client = TestClient(app)
    resp = client.get("/api/v1/trends/series?range=30d")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["window_days"] == 30
    assert "claude-sonnet-4-5" in body["per_model"]
    series = body["per_model"]["claude-sonnet-4-5"]
    assert isinstance(series, list)
    assert len(series) == 30
    # We seeded 30 day-buckets with score_total=0.5 ⇒ mean ×100 = 50.0
    non_zero = [v for v in series if v > 0]
    assert non_zero, "expected some non-zero days"
    for v in non_zero:
        assert v == pytest.approx(50.0)


def test_trends_series_per_operator_optional(db_engine: object) -> None:
    _seed_days(db_engine, 7)
    client = TestClient(app)
    resp = client.get("/api/v1/trends/series?range=7d&show_operators=false")
    assert resp.status_code == 200
    assert resp.json()["per_operator"] == {}

    resp2 = client.get("/api/v1/trends/series?range=7d&show_operators=true")
    assert resp2.status_code == 200
    body = resp2.json()
    assert "self" in body["per_operator"]
    assert len(body["per_operator"]["self"]) == 7


def test_compute_trends_series_zero_days_returns_empty(db_engine: object) -> None:
    series = compute_trends_series(
        Session(db_engine), window_days=0
    )
    assert series.window_days == 0
    assert series.per_model == {}
