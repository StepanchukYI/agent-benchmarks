from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "designer.db"
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


def _seed(engine: object) -> None:
    with Session(engine) as session:
        user = User(github_id="gh-1", handle="alice")
        session.add(user)
        session.commit()
        session.refresh(user)

        repo = RegisteredRepo(user_id=user.id, repo_url="https://github.com/alice/results")
        session.add(repo)
        session.commit()
        session.refresh(repo)

        sub = Submission(
            registered_repo_id=repo.id,
            source_commit_sha="deadbeef",
            source_path="results/x",
            trust_tier="verified",
            ingested_at=datetime.now(UTC),
            model="claude-sonnet-4-5",
            tier="T2",
            dataset_version="0.1.0",
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)

        for i, suite in enumerate(["L0_smoke", "L1_smoke"]):
            tr = TaskResult(
                task_id=f"{suite}_001",
                suite=suite,
                model="claude-sonnet-4-5",
                tier="T2",
                tier_hash="sha256:abc",
                status="completed",
                score_correctness=0.9,
                score_context_eff=0.8,
                score_tool_skill=0.7,
                score_memory=0.6,
                score_latency=0.5,
                score_total=0.7 + i * 0.05,
                cost_usd=0.02,
                latency_ms=2500,
                submission_id=sub.id,
            )
            session.add(tr)
        session.commit()


def test_leaderboard_response_designer_shape(db_engine: object) -> None:
    _seed(db_engine)
    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard")
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert set(body.keys()) >= {"rows", "pillars", "generated_at"}
    assert body["pillars"] == [
        "Correctness",
        "Context",
        "Tool/Skill",
        "Memory",
        "Latency $",
    ]
    assert isinstance(body["rows"], list)
    assert body["rows"], "expected at least one row"

    row = body["rows"][0]
    expected_fields = {
        "model",
        "operator",
        "trust_tier",
        "source_commit_sha",
        "scores",
        "delta",
        "runs",
        "variance",
        "cost_per_task",
        "latency_s",
        "sweep_cost",
        "dataset_pin",
        "tier",
    }
    assert expected_fields.issubset(row.keys())
    assert isinstance(row["scores"], list)
    assert len(row["scores"]) == 5
    # Pillars may be null (no measured data); measured pillars are numeric.
    for v in row["scores"]:
        assert v is None or isinstance(v, (int, float))
    # This fixture scores every pillar, so none should be null here.
    assert all(v is not None for v in row["scores"])
    assert isinstance(row["delta"], list)
    assert len(row["delta"]) == 5
    assert row["model"] == "claude-sonnet-4-5"
    assert row["operator"] == "alice"
    assert row["trust_tier"] == "verified"
    assert row["source_commit_sha"] == "deadbeef"
    assert row["runs"] == 2
    assert row["dataset_pin"]["version"] == "0.1.0"
    assert row["dataset_pin"]["behind"] == 0
    assert row["tier"] == "T2"
    # cost_per_task should equal median of [0.02, 0.02] = 0.02
    assert row["cost_per_task"] == pytest.approx(0.02)
    # latency_s = median(2500ms)/1000 = 2.5
    assert row["latency_s"] == pytest.approx(2.5)
    # sweep_cost = sum of L0_+L1_ task cost = 0.04
    assert row["sweep_cost"] == pytest.approx(0.04)


def _seed_unmeasured_pillars(engine: object) -> None:
    """A model whose task measured correctness + a GENUINE 0.0 latency, with the
    other three pillars NOT measured (None columns). Distinguishes "not measured"
    (None → null in payload) from "measured a real 0.0" (0.0 → numeric in payload)."""
    with Session(engine) as session:
        user = User(github_id="gh-2", handle="bob")
        session.add(user)
        session.commit()
        session.refresh(user)
        repo = RegisteredRepo(user_id=user.id, repo_url="https://github.com/bob/results")
        session.add(repo)
        session.commit()
        session.refresh(repo)
        sub = Submission(
            registered_repo_id=repo.id,
            source_commit_sha="cafe",
            source_path="results/y",
            trust_tier="self_reported",
            ingested_at=datetime.now(UTC),
            model="haiku",
            tier="T0",
            dataset_version="0.1.0",
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        tr = TaskResult(
            task_id="L0_smoke_001",
            suite="L0_smoke",
            model="haiku",
            tier="T0",
            tier_hash="sha256:def",
            status="completed",
            score_correctness=0.9,   # measured
            score_context_eff=None,  # NOT measured
            score_tool_skill=None,   # NOT measured
            score_memory=None,       # NOT measured
            score_latency=0.0,       # measured a genuine zero
            score_total=0.9,
            cost_usd=0.01,
            latency_ms=1000,
            submission_id=sub.id,
        )
        session.add(tr)
        session.commit()


def test_leaderboard_row_nulls_unmeasured_pillars(db_engine: object) -> None:
    _seed_unmeasured_pillars(db_engine)
    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard")
    assert resp.status_code == 200, resp.text
    row = next(r for r in resp.json()["rows"] if r["model"] == "haiku")
    # Pillar order: correctness, context, tool_skill, memory, latency.
    scores = row["scores"]
    assert scores[0] == pytest.approx(90.0)  # correctness measured
    # Context/tool/memory were NOT measured (None column) → null.
    assert scores[1] is None
    assert scores[2] is None
    assert scores[3] is None
    # Latency was MEASURED as a genuine 0.0 → must stay numeric 0.0, NOT null.
    # This is the count-based correctness B7 fixes vs the old 0.0-skip heuristic.
    assert scores[4] == pytest.approx(0.0)
