from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import Run, TaskResult, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine, select


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


def test_create_run_default_returns_422_with_cli_commands(db_engine: object) -> None:
    """POST /runs without dispatch_via_cli=true → 422 + CLI command to copy."""
    client = TestClient(app)
    resp = client.post(
        "/api/v1/runs",
        json={
            "suites": ["L0_smoke"],
            "task_ids": ["L0_001"],
            "models": ["claude-sonnet-4-5"],
            "tier": "T0",
        },
        headers=_h(),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["error"] == "server_side_dispatch_not_implemented"
    assert detail["cli_commands"]
    assert "ab run" in detail["cli_commands"][0]
    assert "--model claude-sonnet-4-5" in detail["cli_commands"][0]


def test_create_run_returns_run_ids_per_model(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/runs",
        json={
            "suites": ["L0_smoke"],
            "task_ids": ["L0_001", "L0_002"],
            "models": ["claude-sonnet-4-5", "codex-cli"],
            "tier": "T2",
            "dataset_version": "0.1.0",
            "repetitions": 2,
            "label": "test-launch",
            "dispatch_via_cli": True,
        },
        headers=_h(),
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert len(body["run_ids"]) == 2
    assert body["label"] == "test-launch"
    assert len(body["cli_commands"]) == 2
    assert "ab run" in body["cli_commands"][0]

    # Each run has expected_total = 2 tasks * 2 repetitions = 4
    with Session(db_engine) as session:  # type: ignore[arg-type]
        runs = session.exec(select(Run)).all()
        assert len(runs) == 2
        for r in runs:
            assert r.expected_total == 4
            assert r.status == "scheduled"
            assert r.label == "test-launch"


def test_create_run_rejects_empty_models(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/runs",
        json={"models": [], "tier": "T0", "suites": []},
        headers=_h(),
    )
    assert resp.status_code == 400


def test_create_run_requires_auth(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.post(
        "/api/v1/runs",
        json={"models": ["m"], "tier": "T0"},
    )
    assert resp.status_code == 401


def test_list_runs_filter_by_status_and_pagination(db_engine: object) -> None:
    client = TestClient(app)
    # Seed via the create endpoint to make sure tenant_id wiring works
    for i in range(5):
        client.post(
            "/api/v1/runs",
            json={
                "suites": ["L0_smoke"],
                "task_ids": ["L0_001"],
                "models": [f"model-{i}"],
                "tier": "T0",
                "repetitions": 1,
                "dispatch_via_cli": True,
            },
            headers=_h(),
        )

    # Force the second run into "completed" status
    with Session(db_engine) as session:  # type: ignore[arg-type]
        runs = session.exec(select(Run).order_by(Run.started_at)).all()
        target = runs[1]
        target.status = "completed"
        session.add(target)
        session.commit()

    listed = client.get("/api/v1/runs", headers=_h()).json()
    assert listed["total"] == 5
    assert len(listed["items"]) == 5

    filtered = client.get("/api/v1/runs?status=completed", headers=_h()).json()
    assert filtered["total"] == 1

    paged = client.get("/api/v1/runs?limit=2&offset=0", headers=_h()).json()
    assert paged["limit"] == 2
    assert paged["offset"] == 0
    assert len(paged["items"]) == 2
    assert paged["total"] == 5


def test_list_runs_rejects_invalid_status(db_engine: object) -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/runs?status=banana", headers=_h())
    assert resp.status_code == 400


def test_get_run_returns_detail_with_task_results(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/runs",
        json={
            "suites": ["L0_smoke"],
            "task_ids": ["L0_001", "L0_002"],
            "models": ["m"],
            "tier": "T0",
            "repetitions": 1,
            "dispatch_via_cli": True,
        },
        headers=_h(),
    ).json()
    run_id = created["run_ids"][0]

    # Seed two task_results — one finished, one in progress
    with Session(db_engine) as session:  # type: ignore[arg-type]
        from uuid import UUID

        rid = UUID(run_id)
        session.add(
            TaskResult(
                run_id=rid,
                task_id="L0_001",
                suite="L0_smoke",
                model="m",
                tier="T0",
                tier_hash="",
                status="completed",
                score_total=0.8,
            )
        )
        session.add(
            TaskResult(
                run_id=rid,
                task_id="L0_002",
                suite="L0_smoke",
                model="m",
                tier="T0",
                tier_hash="",
                status="pending",
            )
        )
        session.commit()

    detail = client.get(f"/api/v1/runs/{run_id}", headers=_h()).json()
    assert detail["id"] == run_id
    assert len(detail["task_results"]) == 2
    # expected_total = 2 * 1 = 2; one finished -> progress_pct = 50.0
    assert detail["expected_total"] == 2
    assert detail["progress_pct"] == 50.0


def test_get_run_other_user_is_404(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/runs",
        json={"models": ["m"], "tier": "T0", "task_ids": ["L0_001"], "dispatch_via_cli": True},
        headers=_h("alice"),
    ).json()
    rid = created["run_ids"][0]
    resp = client.get(f"/api/v1/runs/{rid}", headers=_h("bob"))
    assert resp.status_code == 404


def test_list_runs_isolated_per_user(db_engine: object) -> None:
    client = TestClient(app)
    client.post(
        "/api/v1/runs",
        json={"models": ["m"], "tier": "T0", "task_ids": ["L0_001"], "dispatch_via_cli": True},
        headers=_h("alice"),
    )
    client.post(
        "/api/v1/runs",
        json={"models": ["m"], "tier": "T0", "task_ids": ["L0_001"], "dispatch_via_cli": True},
        headers=_h("bob"),
    )
    a = client.get("/api/v1/runs", headers=_h("alice")).json()
    b = client.get("/api/v1/runs", headers=_h("bob")).json()
    assert a["total"] == 1
    assert b["total"] == 1
    # Ensure each user only sees their own
    with Session(db_engine) as session:  # type: ignore[arg-type]
        users = session.exec(select(User)).all()
        assert len(users) == 2
