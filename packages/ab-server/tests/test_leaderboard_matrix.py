from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from ab_server.leaderboard import compute_matrix
from ab_server.models import (
    RegisteredRepo,
    Submission,
    TaskResult,
    User,
)
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed_basic(session: Session) -> dict[str, UUID]:
    user_a = User(github_id="gh-a", handle="octocat")
    user_b = User(github_id="gh-b", handle="alice")
    session.add(user_a)
    session.add(user_b)
    session.commit()
    session.refresh(user_a)
    session.refresh(user_b)

    repo_a = RegisteredRepo(user_id=user_a.id, repo_url="https://x/a")
    repo_b = RegisteredRepo(user_id=user_b.id, repo_url="https://x/b")
    session.add(repo_a)
    session.add(repo_b)
    session.commit()
    session.refresh(repo_a)
    session.refresh(repo_b)

    ingested = datetime(2026, 5, 10, tzinfo=UTC)
    sub_a_verified = Submission(
        registered_repo_id=repo_a.id,
        source_commit_sha="aaa",
        source_path="results/x",
        trust_tier="verified",
        ingested_at=ingested,
        model="claude-sonnet-4-5",
        tier="T2",
        dataset_version="0.1.0",
    )
    sub_a_self = Submission(
        registered_repo_id=repo_a.id,
        source_commit_sha="bbb",
        source_path="results/y",
        trust_tier="self_reported",
        ingested_at=ingested,
        model="claude-sonnet-4-5",
        tier="T0",
        dataset_version="0.1.0",
    )
    sub_b_verified = Submission(
        registered_repo_id=repo_b.id,
        source_commit_sha="ccc",
        source_path="results/z",
        trust_tier="verified",
        ingested_at=ingested,
        model="gpt-5",
        tier="T2",
        dataset_version="0.1.0",
    )
    session.add_all([sub_a_verified, sub_a_self, sub_b_verified])
    session.commit()
    session.refresh(sub_a_verified)
    session.refresh(sub_a_self)
    session.refresh(sub_b_verified)

    # 3 models × 2 tiers × 2 suites = 12 task_results
    models = ["claude-sonnet-4-5", "gpt-5", "gemini-2-5"]
    tiers = ["T0", "T2"]
    suites = ["L0_smoke", "L1_smoke"]

    # Use submission_a_verified for claude T2 + verified rows; sub_a_self for
    # claude T0 + self_reported; sub_b_verified for gpt rows; gemini unaffiliated.
    sub_for: dict[tuple[str, str], UUID | None] = {
        ("claude-sonnet-4-5", "T2"): sub_a_verified.id,
        ("claude-sonnet-4-5", "T0"): sub_a_self.id,
        ("gpt-5", "T2"): sub_b_verified.id,
        ("gpt-5", "T0"): sub_b_verified.id,
        ("gemini-2-5", "T2"): None,
        ("gemini-2-5", "T0"): None,
    }

    score_map = {
        ("claude-sonnet-4-5", "T2"): 0.9,
        ("claude-sonnet-4-5", "T0"): 0.6,
        ("gpt-5", "T2"): 0.8,
        ("gpt-5", "T0"): 0.5,
        ("gemini-2-5", "T2"): 0.7,
        ("gemini-2-5", "T0"): 0.4,
    }

    for m in models:
        for t in tiers:
            for s in suites:
                tr = TaskResult(
                    task_id=f"{s}_001",
                    suite=s,
                    model=m,
                    tier=t,
                    tier_hash="sha256:abc",
                    status="completed",
                    score_total=score_map[(m, t)],
                    cost_usd=0.01,
                    latency_ms=1000,
                    submission_id=sub_for[(m, t)],
                )
                session.add(tr)
    session.commit()
    return {"user_a": user_a.id, "user_b": user_b.id}


def test_matrix_shape_and_means():
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        matrix = compute_matrix(session)

    assert matrix.suites == ["L0_smoke", "L1_smoke"]
    # 3 models × 2 tiers = 6 rows
    assert len(matrix.rows) == 6

    by_key = {(r.model, r.tier): r for r in matrix.rows}
    claude_t2 = by_key[("claude-sonnet-4-5", "T2")]
    assert pytest.approx(claude_t2.cells["L0_smoke"].score_mean) == 0.9
    assert claude_t2.cells["L0_smoke"].n == 1
    assert pytest.approx(claude_t2.row_mean) == 0.9
    assert "verified" in claude_t2.cells["L0_smoke"].trust_tiers


def test_filter_suites_only():
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        matrix = compute_matrix(session, suites=["L0_smoke"])

    assert matrix.suites == ["L0_smoke"]
    for row in matrix.rows:
        assert "L1_smoke" not in row.cells
        assert "L0_smoke" in row.cells


def test_filter_models_only():
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        matrix = compute_matrix(session, models=["gpt-5"])

    for row in matrix.rows:
        assert row.model == "gpt-5"
    assert len(matrix.rows) == 2  # 2 tiers


def test_filter_tiers_only():
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        matrix = compute_matrix(session, tiers=["T2"])

    for row in matrix.rows:
        assert row.tier == "T2"
    assert len(matrix.rows) == 3  # 3 models


def test_filter_trust_only():
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        matrix = compute_matrix(session, trust=["verified"])

    keys = {(r.model, r.tier) for r in matrix.rows}
    # Only rows with at least one verified submission survive.
    assert ("claude-sonnet-4-5", "T2") in keys
    assert ("gpt-5", "T2") in keys
    assert ("gpt-5", "T0") in keys
    assert ("claude-sonnet-4-5", "T0") not in keys
    # gemini rows have no submission - filter excludes them.
    assert ("gemini-2-5", "T2") not in keys


def test_filter_operator_only():
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        matrix = compute_matrix(session, operator="octocat")

    keys = {(r.model, r.tier) for r in matrix.rows}
    assert ("claude-sonnet-4-5", "T2") in keys
    assert ("claude-sonnet-4-5", "T0") in keys
    assert ("gpt-5", "T2") not in keys


def test_filter_date_range():
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        future = datetime(2026, 6, 1, tzinfo=UTC)
        matrix = compute_matrix(session, date_from=future)

    # All seeded data is before 2026-06-01, so nothing should appear.
    assert matrix.rows == []


def test_filter_combined():
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        matrix = compute_matrix(
            session,
            suites=["L0_smoke"],
            models=["claude-sonnet-4-5"],
            tiers=["T2"],
            trust=["verified"],
        )

    assert len(matrix.rows) == 1
    row = matrix.rows[0]
    assert row.model == "claude-sonnet-4-5"
    assert row.tier == "T2"
    assert list(row.cells.keys()) == ["L0_smoke"]
    assert matrix.filters_applied["suites"] == ["L0_smoke"]


def test_csv_normalization_via_split():
    # Sanity: the API helper is exercised through compute_matrix indirectly,
    # but we can still verify the function tolerates list inputs as-is.
    eng = _engine()
    with Session(eng) as session:
        _seed_basic(session)
        matrix = compute_matrix(session, tiers=["T0", "T2"])
    assert {row.tier for row in matrix.rows} == {"T0", "T2"}
