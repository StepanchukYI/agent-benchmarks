from __future__ import annotations

import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.api import runs as runs_module
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import Run
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
    # Speed up SSE poll loop for tests.
    monkeypatch.setattr(runs_module, "SSE_POLL_INTERVAL_SECONDS", 0.05, raising=True)
    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def _h(user: str = "alice") -> dict[str, str]:
    return {"X-Test-User": user}


def test_stream_emits_progress_and_closes_on_completion(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/runs",
        json={
            "suites": ["L0_smoke"],
            "task_ids": ["L0_001"],
            "models": ["m"],
            "tier": "T0",
            "repetitions": 1,
            "dispatch_via_cli": True,
        },
        headers=_h(),
    ).json()
    run_id = created["run_ids"][0]

    # Flip status to completed after a brief delay so the stream sees an
    # in_progress state first and then the terminal state on the next tick.
    def _complete_after_delay() -> None:
        time.sleep(0.2)
        with Session(db_engine) as session:  # type: ignore[arg-type]
            from uuid import UUID

            run = session.get(Run, UUID(run_id))
            assert run is not None
            run.status = "completed"
            session.add(run)
            session.commit()

    threading.Thread(target=_complete_after_delay, daemon=True).start()

    deadline = time.time() + 5.0
    saw_data = False
    saw_completed = False
    with client.stream(
        "GET", f"/api/v1/runs/{run_id}/stream", headers=_h(), timeout=5.0
    ) as resp:
        assert resp.status_code == 200
        assert "text/event-stream" in resp.headers.get("content-type", "")
        for raw in resp.iter_lines():
            if not raw:
                continue
            if raw.startswith("data:"):
                saw_data = True
                if '"status": "completed"' in raw or '"status":"completed"' in raw:
                    saw_completed = True
                    break
            if time.time() > deadline:
                break

    assert saw_data, "expected at least one data: line"
    assert saw_completed, "expected stream to surface completed status before closing"


def test_stream_404_for_other_user(db_engine: object) -> None:
    client = TestClient(app)
    created = client.post(
        "/api/v1/runs",
        json={"models": ["m"], "tier": "T0", "task_ids": ["L0_001"], "dispatch_via_cli": True},
        headers=_h("alice"),
    ).json()
    rid = created["run_ids"][0]
    resp = client.get(f"/api/v1/runs/{rid}/stream", headers=_h("bob"))
    assert resp.status_code == 404
