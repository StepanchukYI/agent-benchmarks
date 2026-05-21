from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ab_server.api.runs import (
    ESTIMATE_FALLBACK_COST_USD,
    ESTIMATE_FALLBACK_DURATION_SEC,
)
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


def _seed_history(engine: object, task_id: str, costs: list[float], latencies_ms: list[int]) -> None:
    with Session(engine) as session:  # type: ignore[arg-type]
        run = Run(
            tenant_id="self",
            suite="L0_smoke",
            model="claude-sonnet-4-5",
            tier="T2",
            tier_hash="",
            dataset_version="0.1.0",
            status="completed",
            started_at=datetime.now(UTC),
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        for c, l_ms in zip(costs, latencies_ms, strict=True):
            session.add(
                TaskResult(
                    run_id=run.id,
                    task_id=task_id,
                    suite="L0_smoke",
                    model="claude-sonnet-4-5",
                    tier="T2",
                    tier_hash="",
                    status="completed",
                    score_total=0.7,
                    cost_usd=c,
                    latency_ms=l_ms,
                )
            )
        session.commit()


def test_estimate_uses_historical_medians(db_engine: object) -> None:
    # Two tasks, each with three historical samples.
    _seed_history(db_engine, "L0_001", [0.10, 0.20, 0.30], [60_000, 90_000, 120_000])
    _seed_history(db_engine, "L0_002", [0.05, 0.07, 0.09], [30_000, 60_000, 90_000])

    client = TestClient(app)
    resp = client.post(
        "/api/v1/runs/estimate",
        json={
            "suites": ["L0_smoke"],
            "task_ids": ["L0_001", "L0_002"],
            "models": ["claude-sonnet-4-5", "codex-cli"],
            "tier": "T2",
            "repetitions": 2,
            "concurrency": 4,
        },
        headers=_h(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # 2 tasks * 2 models * 2 reps = 8
    assert body["expected_trajectories"] == 8
    # median costs: task1=0.20, task2=0.07 -> sum=0.27; * 2 reps * 2 models = 1.08
    assert body["estimated_cost_usd"] == pytest.approx(1.08, abs=1e-6)
    # median latencies: task1=90s, task2=60s -> avg per-task = 75s
    # duration_min = expected_trajectories * 75s / concurrency / 60
    # = 8 * 75 / 4 / 60 = 2.5 min
    assert body["estimated_duration_min"] == pytest.approx(2.5, abs=1e-6)
    assert body["basis"]["window_days"] == 30
    assert body["basis"]["sample_size_per_task"] == 3


def test_estimate_zero_data_uses_fallback(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/runs/estimate",
        json={
            "suites": ["L0_smoke"],
            "task_ids": ["L0_brand_new"],
            "models": ["claude-sonnet-4-5"],
            "tier": "T2",
            "repetitions": 1,
            "concurrency": 1,
        },
        headers=_h(),
    )
    assert resp.status_code == 200
    body = resp.json()
    # Fallback per task: cost = 0.05 USD, latency = 120s
    assert body["estimated_cost_usd"] == pytest.approx(
        ESTIMATE_FALLBACK_COST_USD, abs=1e-6
    )
    # duration_min = 1 trajectory * 120s / 1 concurrency / 60 = 2.0
    assert body["estimated_duration_min"] == pytest.approx(
        ESTIMATE_FALLBACK_DURATION_SEC / 60.0, abs=1e-6
    )
    assert body["basis"]["sample_size_per_task"] == 0


def test_estimate_rejects_empty_models(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/runs/estimate",
        json={"models": [], "tier": "T0", "task_ids": ["L0_001"]},
        headers=_h(),
    )
    assert resp.status_code == 400


def test_estimate_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/runs/estimate",
        json={"models": ["m"], "tier": "T0", "task_ids": ["L0_001"]},
    )
    assert resp.status_code == 401
