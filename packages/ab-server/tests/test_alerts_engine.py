from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ab_server.alerts.engine import _delta_pct, evaluate_alert
from ab_server.models import AlertRule, Run, TaskResult, User
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed_run_with_score(
    session: Session,
    *,
    suite: str,
    model: str,
    tier: str,
    score: float,
    started_at: datetime,
) -> None:
    run = Run(
        suite=suite,
        model=model,
        tier=tier,
        tier_hash="",
        dataset_version="0.1.0",
        status="completed",
        started_at=started_at,
    )
    session.add(run)
    session.commit()
    session.refresh(run)
    session.add(
        TaskResult(
            run_id=run.id,
            task_id="L1_001",
            suite=suite,
            model=model,
            tier=tier,
            tier_hash="",
            status="completed",
            score_total=score,
            cost_usd=0.01,
            latency_ms=1000,
        )
    )
    session.commit()


def test_delta_pct_handles_zero_prev():
    # When prev=0, fall back to absolute delta * 100.
    assert _delta_pct(0.5, 0.0) == 50.0
    assert _delta_pct(-0.3, 0.0) == -30.0


def test_alert_fires_on_downward_regression():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        user = User(github_id="test:alice", handle="alice")
        session.add(user)
        session.commit()
        session.refresh(user)

        # Prior window: 7-14 days ago, score ~0.9
        for i in range(4):
            _seed_run_with_score(
                session,
                suite="L1_memory",
                model="claude-sonnet-4-5",
                tier="T2",
                score=0.9,
                started_at=now - timedelta(days=10 + i),
            )
        # Current window: 0-6 days ago, score ~0.5
        for i in range(4):
            _seed_run_with_score(
                session,
                suite="L1_memory",
                model="claude-sonnet-4-5",
                tier="T2",
                score=0.5,
                started_at=now - timedelta(days=1 + i),
            )

        rule = AlertRule(
            user_id=user.id,
            name="L1 regression watchdog",
            metric="score_total",
            suite="L1_memory",
            model="claude-sonnet-4-5",
            tier="T2",
            direction="down",
            threshold_pct=5.0,
            window_days=7,
            channels=[],
            enabled=True,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)

        fired = evaluate_alert(session, rule, now=now)
        assert fired is True
        session.refresh(rule)
        assert rule.last_fired_at is not None
        assert rule.last_evaluated_at is not None


def test_alert_does_not_fire_when_stable():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        user = User(github_id="test:alice", handle="alice")
        session.add(user)
        session.commit()
        session.refresh(user)

        # Both windows ~0.85 — under threshold.
        for i in range(4):
            _seed_run_with_score(
                session,
                suite="L1_memory",
                model="claude-sonnet-4-5",
                tier="T2",
                score=0.86,
                started_at=now - timedelta(days=10 + i),
            )
        for i in range(4):
            _seed_run_with_score(
                session,
                suite="L1_memory",
                model="claude-sonnet-4-5",
                tier="T2",
                score=0.85,
                started_at=now - timedelta(days=1 + i),
            )

        rule = AlertRule(
            user_id=user.id,
            name="stable",
            metric="score_total",
            suite="L1_memory",
            model="claude-sonnet-4-5",
            tier="T2",
            direction="down",
            threshold_pct=5.0,
            window_days=7,
            channels=[],
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)

        fired = evaluate_alert(session, rule, now=now)
        assert fired is False
        session.refresh(rule)
        assert rule.last_fired_at is None
        assert rule.last_evaluated_at is not None


def test_alert_does_not_fire_when_disabled():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        user = User(github_id="test:alice", handle="alice")
        session.add(user)
        session.commit()
        session.refresh(user)
        # Seed an unambiguous regression
        for i in range(3):
            _seed_run_with_score(
                session,
                suite="L1_memory",
                model="m",
                tier="T2",
                score=0.9,
                started_at=now - timedelta(days=10 + i),
            )
        for i in range(3):
            _seed_run_with_score(
                session,
                suite="L1_memory",
                model="m",
                tier="T2",
                score=0.4,
                started_at=now - timedelta(days=1 + i),
            )
        rule = AlertRule(
            user_id=user.id,
            name="disabled",
            suite="L1_memory",
            model="m",
            tier="T2",
            direction="down",
            threshold_pct=5.0,
            window_days=7,
            channels=[],
            enabled=False,
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        assert evaluate_alert(session, rule, now=now) is False
        session.refresh(rule)
        assert rule.last_fired_at is None


def test_alert_fires_up_direction():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        user = User(github_id="test:alice", handle="alice")
        session.add(user)
        session.commit()
        session.refresh(user)
        # Improvement: prior ~0.5 -> current ~0.9
        for i in range(3):
            _seed_run_with_score(
                session,
                suite="L0_smoke",
                model="m",
                tier="T0",
                score=0.5,
                started_at=now - timedelta(days=10 + i),
            )
        for i in range(3):
            _seed_run_with_score(
                session,
                suite="L0_smoke",
                model="m",
                tier="T0",
                score=0.9,
                started_at=now - timedelta(days=1 + i),
            )
        rule = AlertRule(
            user_id=user.id,
            name="improvements",
            suite="L0_smoke",
            model="m",
            tier="T0",
            direction="up",
            threshold_pct=10.0,
            window_days=7,
            channels=[],
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        assert evaluate_alert(session, rule, now=now) is True


def test_alert_no_data_does_not_fire():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        user = User(github_id="test:alice", handle="alice")
        session.add(user)
        session.commit()
        session.refresh(user)
        rule = AlertRule(
            user_id=user.id,
            name="no-data",
            suite="L0_smoke",
            model="never-seen",
            tier="T0",
            direction="down",
            threshold_pct=5.0,
            window_days=7,
            channels=[],
        )
        session.add(rule)
        session.commit()
        session.refresh(rule)
        assert evaluate_alert(session, rule, now=now) is False
        session.refresh(rule)
        assert rule.last_evaluated_at is not None
        assert rule.last_fired_at is None
