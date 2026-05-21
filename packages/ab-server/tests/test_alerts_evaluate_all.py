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
def db_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    monkeypatch.setenv("AB_TEST_AUTH", "1")
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
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


def _h(user: str = "alice") -> dict[str, str]:
    return {"X-Test-User": user}


def _seed_regression(engine: object, *, suite: str, model: str, tier: str) -> None:
    """Seed a sharp downward regression: prior ~0.9, current ~0.4."""
    now = datetime.now(UTC)
    with Session(engine) as session:  # type: ignore[arg-type]
        for offset, score in (
            (10, 0.9), (11, 0.9), (12, 0.9),
            (1, 0.4), (2, 0.4), (3, 0.4),
        ):
            run = Run(
                suite=suite,
                model=model,
                tier=tier,
                tier_hash="",
                dataset_version="0.1.0",
                status="completed",
                started_at=now - timedelta(days=offset),
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            session.add(
                TaskResult(
                    run_id=run.id,
                    task_id="L1_001",
                    suite=suite,
                    model=model,
                    tier=tier,
                    tier_hash="",
                    status="completed",
                    score_total=score,
                    cost_usd=0.01,
                    latency_ms=1000,
                )
            )
            session.commit()


def test_evaluate_all_returns_counts_and_fired(db_engine: object) -> None:
    client = TestClient(app)
    _seed_regression(db_engine, suite="L1_memory", model="m1", tier="T2")

    # Create two rules: one will fire, one targets a non-existent model.
    client.post(
        "/api/v1/alerts",
        json={
            "name": "firing rule",
            "metric": "score_total",
            "suite": "L1_memory",
            "model": "m1",
            "tier": "T2",
            "direction": "down",
            "threshold_pct": 5.0,
            "window_days": 7,
            "channels": [],
        },
        headers=_h(),
    )
    client.post(
        "/api/v1/alerts",
        json={
            "name": "idle rule",
            "metric": "score_total",
            "suite": "L1_memory",
            "model": "never-seen",
            "tier": "T2",
            "direction": "down",
            "threshold_pct": 5.0,
            "window_days": 7,
            "channels": [],
        },
        headers=_h(),
    )

    resp = client.post("/api/v1/alerts/evaluate", headers=_h())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["evaluated"] == 2
    assert len(body["fired"]) == 1
    assert body["fired"][0]["name"] == "firing rule"
    assert body["fired"][0]["state"] == "firing"
