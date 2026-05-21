from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ab_server.leaderboard import compute_trends
from ab_server.models import Run, TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def test_trends_returns_one_point_per_day():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        for day in range(30):
            started = now - timedelta(days=day)
            run = Run(
                suite="L0_smoke",
                model="claude-sonnet-4-5",
                tier="T2",
                tier_hash="sha256:abc",
                dataset_version="0.1.0",
                started_at=started,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            tr = TaskResult(
                task_id="L0_001",
                suite="L0_smoke",
                model="claude-sonnet-4-5",
                tier="T2",
                tier_hash="sha256:abc",
                status="completed",
                score_total=0.5 + day * 0.01,
                cost_usd=0.01,
                latency_ms=1000,
                run_id=run.id,
            )
            session.add(tr)
        session.commit()

        series = compute_trends(
            session,
            model="claude-sonnet-4-5",
            suite="L0_smoke",
            tier="T2",
            days=30,
        )

    # 30 distinct days seeded; some boundary skew is possible if `today`
    # equals seeded day 0, but counts should be >= 29 and <= 31.
    assert 29 <= len(series.points) <= 31
    assert series.model == "claude-sonnet-4-5"
    assert series.suite == "L0_smoke"
    assert series.tier == "T2"
    for p in series.points:
        assert p.n == 1
        assert 0.5 <= p.score_mean <= 0.5 + 29 * 0.01 + 1e-9


def test_trends_zero_days_returns_empty():
    eng = _engine()
    with Session(eng) as session:
        series = compute_trends(
            session, model="m", suite="s", tier="T0", days=0
        )
    assert series.points == []
