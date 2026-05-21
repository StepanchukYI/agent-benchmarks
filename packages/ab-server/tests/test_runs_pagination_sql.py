"""H8: list_runs must paginate at the SQL layer, not slice in Python.

We seed 25 runs, request a window in the middle, and assert (a) the
response contains exactly `limit` items, (b) `total` reflects all 25,
and (c) the underlying engine actually issued OFFSET/LIMIT SQL.

We build a fresh app per test (with rate limiting disabled) to avoid
sharing rate-limit bucket state with other tests that import the global
``ab_server.main:app``.
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from uuid import uuid4

import pytest
from ab_server.config import Settings
from ab_server.db import get_session
from ab_server.main import create_app
from ab_server.models import Run, User
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[tuple[FastAPI, object]]:
    monkeypatch.setenv("AB_TEST_AUTH", "1")
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)

    # rate_limit_per_minute=0 keeps the middleware out of the chain, so this
    # test's traffic doesn't drain any shared bucket.
    app = create_app(Settings(rate_limit_per_minute=0, ab_test_auth=True))

    def _override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    try:
        yield app, engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def _h(user: str = "alice") -> dict[str, str]:
    return {"X-Test-User": user}


def _seed_run(session: Session, tenant_id: str, idx: int) -> None:
    # Direct insert; bypasses the create endpoint to avoid the per-request
    # tenant_id lookup churn and to control the count precisely.
    session.add(
        Run(
            id=uuid4(),
            tenant_id=tenant_id,
            suite="L0_smoke",
            model=f"model-{idx:02d}",
            tier="T0",
            tier_hash="",
            dataset_version="ab-datasets==0.0.1",
            status="scheduled",
        )
    )
    session.commit()


def _bootstrap_user(client: TestClient, engine: object) -> str:
    """First authenticated request creates the User row; return its id."""
    r = client.get("/api/v1/runs", headers=_h())
    assert r.status_code == 200, r.text
    with Session(engine) as session:  # type: ignore[arg-type]
        alice = session.exec(select(User).where(User.handle == "alice")).first()
        assert alice is not None
        return str(alice.id)


def test_pagination_returns_total_and_window(env: tuple[FastAPI, object]) -> None:
    app, engine = env
    client = TestClient(app)
    tenant_id = _bootstrap_user(client, engine)

    with Session(engine) as session:  # type: ignore[arg-type]
        for i in range(25):
            _seed_run(session, tenant_id, i)

    body = client.get("/api/v1/runs?limit=10&offset=10", headers=_h()).json()
    assert body["total"] == 25
    assert body["limit"] == 10
    assert body["offset"] == 10
    assert len(body["items"]) == 10


def test_pagination_emits_sql_offset_limit(env: tuple[FastAPI, object]) -> None:
    """Capture the SQL statements and assert OFFSET/LIMIT are present."""
    app, engine = env
    client = TestClient(app)
    tenant_id = _bootstrap_user(client, engine)

    with Session(engine) as session:  # type: ignore[arg-type]
        for i in range(25):
            _seed_run(session, tenant_id, i)

    captured: list[str] = []

    def before_cursor_execute(
        conn, cursor, statement, parameters, context, executemany
    ) -> None:
        captured.append(statement)

    event.listen(engine, "before_cursor_execute", before_cursor_execute)
    try:
        resp = client.get("/api/v1/runs?limit=10&offset=10", headers=_h())
    finally:
        event.remove(engine, "before_cursor_execute", before_cursor_execute)

    assert resp.status_code == 200
    # Look for the SELECT that pages Run, and verify LIMIT/OFFSET in it.
    paged = [
        s
        for s in captured
        if "from runs" in s.lower() and "limit" in s.lower() and "offset" in s.lower()
    ]
    assert paged, f"expected a paginated SQL statement, got: {captured!r}"

    # Also: a separate COUNT(*) query should have been emitted (not a fetch-all).
    count_stmts = [
        s for s in captured if "count(" in s.lower() and "from runs" in s.lower()
    ]
    assert count_stmts, f"expected COUNT query, got: {captured!r}"


def test_pagination_with_status_filter_counts_filtered_total(
    env: tuple[FastAPI, object],
) -> None:
    app, engine = env
    client = TestClient(app)
    tenant_id = _bootstrap_user(client, engine)

    with Session(engine) as session:  # type: ignore[arg-type]
        for i in range(25):
            _seed_run(session, tenant_id, i)
        # Promote 7 rows to "completed".
        all_runs = session.exec(select(Run)).all()
        for r in all_runs[:7]:
            r.status = "completed"
            session.add(r)
        session.commit()

    filtered = client.get(
        "/api/v1/runs?status=completed&limit=5&offset=0", headers=_h()
    ).json()
    assert filtered["total"] == 7
    assert len(filtered["items"]) == 5
