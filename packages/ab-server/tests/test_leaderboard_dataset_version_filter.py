from __future__ import annotations

from datetime import UTC, datetime

from ab_server.leaderboard import compute_matrix
from ab_server.models import Run, TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed_versions(session: Session) -> None:
    now = datetime.now(UTC)
    for version, model_name, score in [
        ("0.1.0", "claude-sonnet-4-5", 0.7),
        ("0.2.0", "gpt-5", 0.8),
    ]:
        run = Run(
            suite="L0_smoke",
            model=model_name,
            tier="T2",
            tier_hash="sha256:abc",
            dataset_version=version,
            started_at=now,
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        tr = TaskResult(
            task_id="L0_001",
            suite="L0_smoke",
            model=model_name,
            tier="T2",
            tier_hash="sha256:abc",
            status="completed",
            score_total=score,
            cost_usd=0.0,
            latency_ms=100,
            run_id=run.id,
        )
        session.add(tr)
    session.commit()


def test_dataset_version_filter_limits_matrix():
    eng = _engine()
    with Session(eng) as session:
        _seed_versions(session)

        all_matrix = compute_matrix(session)
        assert {r.model for r in all_matrix.rows} == {
            "claude-sonnet-4-5",
            "gpt-5",
        }

        v1_matrix = compute_matrix(session, dataset_versions=["0.1.0"])
        assert {r.model for r in v1_matrix.rows} == {"claude-sonnet-4-5"}
        assert v1_matrix.filters_applied["dataset_versions"] == ["0.1.0"]

        v2_matrix = compute_matrix(session, dataset_versions=["0.2.0"])
        assert {r.model for r in v2_matrix.rows} == {"gpt-5"}

        both = compute_matrix(session, dataset_versions=["0.1.0", "0.2.0"])
        assert {r.model for r in both.rows} == {"claude-sonnet-4-5", "gpt-5"}
