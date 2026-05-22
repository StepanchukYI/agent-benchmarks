from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from ab_server.leaderboard import compute_overview
from ab_server.models import AlertRule, Run, TaskResult, User
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
    # No alert rules seeded → real count is 0 (not a hardcoded literal).
    assert overview.alerts_count_window == 0
    # No actioned/acknowledged concept on AlertRule, and no scheduled
    # full-sweep mechanism — both surfaced as honest None.
    assert overview.alerts_actioned is None
    assert overview.last_full_sweep_at is not None
    assert overview.last_full_sweep_cadence is None
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
    assert overview.alerts_count_window == 0
    assert overview.alerts_actioned is None
    assert overview.last_full_sweep_cadence is None


def _add_alert(session: Session, *, name: str, last_fired_at: datetime | None) -> None:
    user = User(github_id=f"gh-{name}", handle=name, avatar_url=None)
    session.add(user)
    session.commit()
    session.refresh(user)
    session.add(
        AlertRule(
            id=uuid4(),
            user_id=user.id,
            name=name,
            window_days=7,
            last_fired_at=last_fired_at,
        )
    )
    session.commit()


def test_overview_alerts_count_reflects_fired_rules_in_window():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        # Fired 2 days ago → inside the 7-day window.
        _add_alert(session, name="fired-recent", last_fired_at=now - timedelta(days=2))
        # Fired 30 days ago → outside the window.
        _add_alert(session, name="fired-old", last_fired_at=now - timedelta(days=30))
        # Never fired → not counted.
        _add_alert(session, name="never-fired", last_fired_at=None)
        overview = compute_overview(session, window_days=7)

    assert overview.alerts_count_window == 1
    assert overview.alerts_actioned is None
