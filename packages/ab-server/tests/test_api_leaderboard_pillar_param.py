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
    db_path = tmp_path / "pillar.db"
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


def _seed_two_models(engine: object) -> None:
    """Seed two models with inverted pillar profiles.

    model_a: high correctness (0.9), low tool_skill (0.1)
    model_b: low correctness (0.2), high tool_skill (0.95)

    Default sort (sum of pillars) and per-pillar sort should differ.
    """
    with Session(engine) as session:
        user = User(github_id="gh-1", handle="alice")
        session.add(user)
        session.commit()
        session.refresh(user)

        repo = RegisteredRepo(
            user_id=user.id, repo_url="https://github.com/alice/results"
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)

        for model, corr, ctx, tool, mem, lat, total in [
            ("model_a", 0.9, 0.5, 0.1, 0.5, 0.5, 0.5),
            ("model_b", 0.2, 0.5, 0.95, 0.5, 0.5, 0.54),
        ]:
            sub = Submission(
                registered_repo_id=repo.id,
                source_commit_sha=f"sha-{model}",
                source_path=f"results/{model}",
                trust_tier="verified",
                ingested_at=datetime.now(UTC),
                model=model,
                tier="T2",
                dataset_version="0.1.0",
            )
            session.add(sub)
            session.commit()
            session.refresh(sub)

            tr = TaskResult(
                task_id="L0_001",
                suite="L0_smoke",
                model=model,
                tier="T2",
                tier_hash="sha256:abc",
                status="completed",
                score_correctness=corr,
                score_context_eff=ctx,
                score_tool_skill=tool,
                score_memory=mem,
                score_latency=lat,
                score_total=total,
                cost_usd=0.02,
                latency_ms=1000,
                submission_id=sub.id,
            )
            session.add(tr)
        session.commit()


def test_leaderboard_no_pillar_returns_default_shape(db_engine: object) -> None:
    _seed_two_models(db_engine)
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
    assert len(body["rows"]) == 2
    for row in body["rows"]:
        assert isinstance(row["scores"], list)
        assert len(row["scores"]) == 5


def test_leaderboard_pillar_correctness_sorts_by_correctness(
    db_engine: object,
) -> None:
    _seed_two_models(db_engine)
    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard?pillar=correctness")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert len(rows) == 2
    # model_a has correctness 0.9 -> 90.0; model_b has 0.2 -> 20.0
    assert rows[0]["model"] == "model_a"
    assert rows[1]["model"] == "model_b"
    assert rows[0]["scores"][0] > rows[1]["scores"][0]


def test_leaderboard_pillar_tool_skill_sorts_by_tool_skill(
    db_engine: object,
) -> None:
    _seed_two_models(db_engine)
    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard?pillar=tool_skill")
    assert resp.status_code == 200, resp.text
    rows = resp.json()["rows"]
    assert len(rows) == 2
    # model_b has tool_skill 0.95; model_a has 0.1
    assert rows[0]["model"] == "model_b"
    assert rows[1]["model"] == "model_a"
    # scores[2] is the tool_skill position
    assert rows[0]["scores"][2] > rows[1]["scores"][2]


def test_leaderboard_invalid_pillar_returns_422(db_engine: object) -> None:
    _seed_two_models(db_engine)
    client = TestClient(app)
    resp = client.get("/api/v1/leaderboard?pillar=not_a_pillar")
    assert resp.status_code == 422, resp.text
