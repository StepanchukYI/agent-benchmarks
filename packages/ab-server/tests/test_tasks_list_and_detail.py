from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def client(tmp_path: Path) -> Iterator[TestClient]:
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    def _override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    c = TestClient(app)
    try:
        yield c
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_list_tasks_returns_shipped_tasks(client: TestClient) -> None:
    resp = client.get("/api/v1/tasks")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    ids = {item["id"] for item in body["items"]}
    expected_l0 = {"L0_001", "L0_002", "L0_003", "L0_004", "L0_005"}
    assert expected_l0.issubset(ids), f"missing L0 tasks; got {ids}"
    layers = {item["layer"] for item in body["items"]}
    assert "L2" in layers
    assert "L3" in layers
    assert "L4" in layers
    for item in body["items"]:
        assert "runs_count_30d" in item
        assert "required_tier" in item
        assert "trust_tier_ceiling" in item
        assert "has_fixtures" in item


def test_get_task_detail_with_stats(client: TestClient) -> None:
    resp = client.get("/api/v1/tasks/L0_001")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == "L0_001"
    assert body["layer"] == "L0"
    assert body["suite"] == "file-ops"
    assert isinstance(body["acceptance_criteria"], list)
    assert len(body["acceptance_criteria"]) >= 1
    assert isinstance(body["scorer_chain"], list)
    # Lever B renamed the file-ops scorer from `file_diff` to
    # `file_diff_and_invariants` (adds fixture-file-unchanged checks).
    assert any(s["name"] == "file_diff_and_invariants" for s in body["scorer_chain"])
    stats = body["stats"]
    assert "pass_rate_30d" in stats
    assert "median_cost_usd" in stats
    assert "median_latency_ms" in stats
    assert "median_turns" in stats
    assert "runs_count_30d" in stats
    assert stats["runs_count_30d"] == 0
    assert stats["median_turns"] is None


def test_get_task_unknown_id_404(client: TestClient) -> None:
    resp = client.get("/api/v1/tasks/L0_999_doesnotexist")
    assert resp.status_code == 404
