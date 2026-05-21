"""Contract tests: backend response shapes match what designer's hooks expect.

Each test hits a real endpoint via FastAPI TestClient with a seeded in-memory
SQLite DB and asserts the JSON shape matches the TypeScript interface in
`packages/ab-leaderboard/src/lib/types.ts` (sync'd via `docs/schemas/`).

If you change a shape on either side, this test fails — that's the point.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import (
    RegisteredRepo,
    Run,
    ScorerVerdictRow,
    Submission,
    TaskResult,
    User,
)
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture(autouse=True)
def _test_auth_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Scoped per-test so we don't leak env into other test files."""
    monkeypatch.setenv("AB_TEST_AUTH", "1")


@pytest.fixture()
def db(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    _seed(engine)

    def _override() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override
    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def _seed(engine: object) -> None:
    """Seed 2 users, 2 repos, 6 submissions, 12 task_results, spread over last 30 days."""
    with Session(engine) as session:
        alice = User(github_id="alice-id", handle="alice", avatar_url=None)
        bob = User(github_id="bob-id", handle="bob", avatar_url=None)
        session.add_all([alice, bob])
        session.commit()
        session.refresh(alice)
        session.refresh(bob)

        repo_a = RegisteredRepo(
            user_id=alice.id,
            repo_url="https://github.com/alice/results",
            default_branch="main",
            sync_cursor="aaaaa",
            last_synced_at=datetime.now(UTC),
            is_public=True,
        )
        repo_b = RegisteredRepo(
            user_id=bob.id,
            repo_url="https://github.com/bob/results",
            default_branch="main",
            sync_cursor="bbbbb",
            last_synced_at=datetime.now(UTC),
            is_public=True,
        )
        session.add_all([repo_a, repo_b])
        session.commit()
        session.refresh(repo_a)
        session.refresh(repo_b)

        models = ["claude-sonnet-4-5", "claude-opus-4-1", "gpt-5"]
        suites = ["file-ops", "schema-fill"]

        now = datetime.now(UTC)
        for i in range(12):
            model = models[i % len(models)]
            suite = suites[i % len(suites)]
            day_offset = i * 2
            repo = repo_a if i % 2 == 0 else repo_b
            sub = Submission(
                registered_repo_id=repo.id,
                source_commit_sha=f"sha{i:04d}",
                source_path=f"results/run-{i:02d}",
                trust_tier="verified" if i % 3 == 0 else "self_reported",
                ingested_at=now - timedelta(days=day_offset),
                re_scored_at=now - timedelta(days=day_offset, hours=-1),
                discrepancy_pct=0.001,
                model=model,
                tier="T0",
                dataset_version="0.0.1",
            )
            session.add(sub)
            session.flush()
            tr = TaskResult(
                submission_id=sub.id,
                task_id=f"L0_{i:03d}",
                suite=suite,
                model=model,
                tier="T0",
                tier_hash=f"hash{i:04d}",
                status="completed",
                score_correctness=0.85 + (i % 5) * 0.02,
                score_context_eff=0.80,
                score_tool_skill=0.78,
                score_memory=0.82,
                score_latency=0.65,
                score_total=0.80 + (i % 5) * 0.015,
                cost_usd=0.04 + (i % 3) * 0.01,
                latency_ms=12000 + i * 500,
                trajectory_blob_ref=f"results/run-{i:02d}",
            )
            session.add(tr)
            session.flush()
            v = ScorerVerdictRow(
                task_result_id=tr.id,
                scorer_name="file_diff",
                kind="deterministic",
                pass_=True,
                score=tr.score_total or 0.0,
                detail={"ok": True},
            )
            session.add(v)
        session.commit()

        run = Run(
            tenant_id="self",
            suite="L0_smoke",
            model="claude-sonnet-4-5",
            tier="T0",
            tier_hash="seedhash",
            dataset_version="0.0.1",
            status="completed",
            started_at=now - timedelta(hours=1),
            finished_at=now,
            cost_total_usd=0.5,
            expected_total=5,
            label="seed-run",
        )
        session.add(run)
        session.commit()


client = TestClient(app)


def test_leaderboard_designer_shape(db: object) -> None:
    """LeaderboardResponse {rows, pillars, generated_at} with LeaderboardRow shape."""
    response = client.get("/api/v1/leaderboard")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) >= {"rows", "pillars", "generated_at"}
    assert isinstance(body["pillars"], list)
    assert len(body["pillars"]) == 5
    assert isinstance(body["rows"], list)
    if body["rows"]:
        row = body["rows"][0]
        for k in (
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
        ):
            assert k in row, f"row missing field {k}: {row}"
        assert isinstance(row["scores"], list) and len(row["scores"]) == 5
        assert isinstance(row["delta"], list) and len(row["delta"]) == 5
        assert set(row["dataset_pin"].keys()) >= {"version", "behind"}


def test_leaderboard_pareto(db: object) -> None:
    response = client.get("/api/v1/leaderboard/pareto")
    assert response.status_code == 200, response.text


def test_trends_overview(db: object) -> None:
    response = client.get("/api/v1/trends/overview")
    assert response.status_code == 200, response.text


def test_trends_series_designer_shape(db: object) -> None:
    """{per_model: {model: float[]}, per_operator: {handle: float[]}, window_days}."""
    response = client.get("/api/v1/trends/series?range=30d&show_operators=true")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) >= {"per_model", "per_operator", "window_days"}
    assert isinstance(body["per_model"], dict)
    assert isinstance(body["per_operator"], dict)
    assert body["window_days"] == 30


def test_trends_regressions(db: object) -> None:
    response = client.get("/api/v1/trends/regressions?direction=down")
    assert response.status_code == 200


def test_trends_ci_gate(db: object) -> None:
    response = client.get("/api/v1/trends/ci-gate")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "status" in body


def test_operators_endpoint_shape(db: object) -> None:
    response = client.get("/api/v1/operators")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    # We seeded users alice + bob; expect at least them + self synthetic.
    handles = {o["handle"] for o in body if isinstance(o, dict)}
    assert handles, body
    if body:
        op = body[0]
        for k in ("handle", "name", "initials", "color", "trust_default"):
            assert k in op, f"operator missing {k}: {op}"


def test_models_endpoint_shape(db: object) -> None:
    response = client.get("/api/v1/models")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    if body:
        m = body[0]
        for k in ("id", "short", "vendor", "harness", "capabilities", "cost_per_1k_in", "cost_per_1k_out"):
            assert k in m, f"model missing {k}: {m}"


def test_account_repos_endpoint_shape(db: object) -> None:
    response = client.get(
        "/api/v1/account/repos", headers={"X-Test-User": "alice"}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)


def test_account_privacy_rules_shape(db: object) -> None:
    response = client.get("/api/v1/account/privacy-rules")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, list)
    if body:
        for k in ("name", "pattern", "replacement"):
            assert k in body[0], f"rule missing {k}: {body[0]}"


def test_tasks_list_shape(db: object) -> None:
    response = client.get("/api/v1/tasks")
    assert response.status_code == 200, response.text
    body = response.json()
    assert isinstance(body, (list, dict))


def test_tiers_list(db: object) -> None:
    response = client.get("/api/v1/tiers")
    assert response.status_code == 200, response.text


def test_runs_list(db: object) -> None:
    response = client.get(
        "/api/v1/runs", headers={"X-Test-User": "alice"}
    )
    assert response.status_code == 200, response.text


def test_alerts_list(db: object) -> None:
    response = client.get(
        "/api/v1/alerts", headers={"X-Test-User": "alice"}
    )
    assert response.status_code == 200, response.text


def test_submissions_list(db: object) -> None:
    response = client.get("/api/v1/submissions")
    assert response.status_code == 200, response.text
    body = response.json()
    assert "items" in body


def test_submissions_privacy_scan_404_when_missing(db: object) -> None:
    """Privacy-scan endpoint exists and returns 404 for nonexistent submissions."""
    fake_id = str(uuid4())
    response = client.get(f"/api/v1/submissions/{fake_id}/privacy-scan")
    assert response.status_code == 404


def test_healthz(db: object) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_lists_all_designer_endpoints(db: object) -> None:
    """Every endpoint designer's `endpoints` map references must be in OpenAPI."""
    spec = app.openapi()
    paths = set(spec.get("paths", {}).keys())
    required = {
        "/api/v1/leaderboard",
        "/api/v1/leaderboard/pareto",
        "/api/v1/trends",
        "/api/v1/trends/overview",
        "/api/v1/trends/regressions",
        "/api/v1/trends/ci-gate",
        "/api/v1/trends/series",
        "/api/v1/runs",
        "/api/v1/runs/{id}",
        "/api/v1/runs/estimate",
        "/api/v1/runs/{id}/stream",
        "/api/v1/runs/{id}/trajectories/{task_id}",
        "/api/v1/submissions",
        "/api/v1/submissions/{id}",
        "/api/v1/submissions/{id}/trajectory",
        "/api/v1/submissions/{id}/privacy-scan",
        "/api/v1/tasks",
        "/api/v1/tasks/{id}",
        "/api/v1/tiers",
        "/api/v1/presets",
        "/api/v1/presets/{id}",
        "/api/v1/alerts",
        "/api/v1/alerts/{id}",
        "/api/v1/alerts/evaluate",
        "/api/v1/operators",
        "/api/v1/models",
        "/api/v1/account/repos",
        "/api/v1/account/privacy-rules",
    }
    missing = required - paths
    assert not missing, f"missing endpoints: {sorted(missing)}\n\nhave: {sorted(paths)}"


def _dump(obj: object) -> str:
    return json.dumps(obj, default=str, indent=2)
