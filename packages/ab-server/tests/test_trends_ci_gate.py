from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ab_server.leaderboard import compute_ci_gate
from ab_server.models import Run, TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed_recent(session: Session, *, cur_score: float, prev_score: float) -> None:
    now = datetime.now(UTC)
    # 4 days of data: days 0..1 = "current 48h", days 2..3 = "prior 48h".
    for day in range(4):
        started = now - timedelta(days=day, hours=1)
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
        score = cur_score if day < 2 else prev_score
        tr = TaskResult(
            task_id="L0_001",
            suite="L0_smoke",
            model="claude-sonnet-4-5",
            tier="T2",
            tier_hash="sha256:abc",
            status="completed",
            score_total=score,
            cost_usd=0.01,
            latency_ms=100,
            run_id=run.id,
        )
        session.add(tr)
    session.commit()


def test_ci_gate_passing_when_stable():
    eng = _engine()
    with Session(eng) as session:
        _seed_recent(session, cur_score=0.80, prev_score=0.80)
        gate = compute_ci_gate(session)
    assert gate.status == "passing"
    assert gate.blocked_merges_48h == 0
    assert gate.threshold_pct == 0.05


def test_ci_gate_failing_when_regression():
    eng = _engine()
    with Session(eng) as session:
        _seed_recent(session, cur_score=0.60, prev_score=0.80)
        gate = compute_ci_gate(session)
    assert gate.status == "failing"
    assert gate.blocked_merges_48h >= 1
    assert gate.threshold_pct == 0.05
