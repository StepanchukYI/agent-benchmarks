from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import TaskResult
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "models.db"
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


def test_models_endpoint_returns_catalog(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    ids = {m["id"] for m in items}
    assert "claude-sonnet-4-5" in ids

    sample = next(m for m in items if m["id"] == "claude-sonnet-4-5")
    expected_keys = {
        "id",
        "short",
        "vendor",
        "harness",
        "capabilities",
        "cost_per_1k_in",
        "cost_per_1k_out",
    }
    assert expected_keys.issubset(sample.keys())
    assert sample["vendor"] == "anthropic"
    assert sample["cost_per_1k_in"] > 0


def test_models_endpoint_emits_unknown_for_db_only_model(db_engine: object) -> None:
    with Session(db_engine) as session:
        tr = TaskResult(
            task_id="L0_001",
            suite="L0_smoke",
            model="custom-model-x",
            tier="T0",
            tier_hash="sha256:abc",
            status="completed",
            score_total=0.5,
            cost_usd=0.0,
            latency_ms=0,
        )
        session.add(tr)
        session.commit()

    client = TestClient(app)
    resp = client.get("/api/v1/models")
    assert resp.status_code == 200
    items = resp.json()
    by_id = {m["id"]: m for m in items}
    assert "custom-model-x" in by_id
    assert by_id["custom-model-x"]["vendor"] == "unknown"
