from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ab_server.leaderboard import compute_overview
from ab_server.models import Run, TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed(session: Session) -> None:
    now = datetime.now(UTC)
    for day in range(14):
        started = now - timedelta(days=day, hours=1)
        run = Run(
            suite="L0_smoke",
            model="claude-sonnet-4-5",
            tier="T2",
            tier_hash="sha256:abc",
            dataset_version="0.1.0",
            started_at=started,
            finished_at=started + timedelta(minutes=10),
            status="completed",
        )
        session.add(run)
        session.commit()
        session.refresh(run)
        score = 0.70 if day < 7 else 0.80
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


def test_overview_fields_and_types():
    eng = _engine()
    with Session(eng) as session:
        _seed(session)
        overview = compute_overview(session, window_days=7)

    assert overview.window_days == 7
    assert isinstance(overview.active_regressions_count, int)
    assert isinstance(overview.improvements_count, int)
    assert overview.ci_gate_status in ("passing", "failing")
    assert isinstance(overview.ci_gate_blocked_merges_48h, int)
    assert overview.alerts_count_window == 0
    assert overview.alerts_actioned == 0
    assert overview.last_full_sweep_at is not None
    assert overview.last_full_sweep_cadence == "scheduled · 03:00 daily"
    # 0.70 < 0.80 ⇒ regression detected.
    assert overview.active_regressions_count >= 1


def test_overview_empty_db_returns_zero_counts():
    eng = _engine()
    with Session(eng) as session:
        overview = compute_overview(session, window_days=7)

    assert overview.active_regressions_count == 0
    assert overview.improvements_count == 0
    assert overview.ci_gate_status == "passing"
    assert overview.ci_gate_blocked_merges_48h == 0
    assert overview.last_full_sweep_at is None
