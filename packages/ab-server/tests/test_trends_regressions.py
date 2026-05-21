from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ab_server.leaderboard import compute_regressions
from ab_server.models import Run, TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed_two_models(session: Session) -> None:
    now = datetime.now(UTC)
    # 14 days of data per model. Day 0..6 = current window. Day 7..13 = prior.
    # Model A: prior 0.80, current 0.70 → delta = -0.10 (regression).
    # Model B: prior 0.60, current 0.68 → delta = +0.08 (improvement).
    plan = [
        ("model-a", 0.80, 0.70),
        ("model-b", 0.60, 0.68),
    ]
    for model_name, prev_score, cur_score in plan:
        for day in range(14):
            started = now - timedelta(days=day, hours=1)
            run = Run(
                suite="L0_smoke",
                model=model_name,
                tier="T2",
                tier_hash="sha256:abc",
                dataset_version="0.1.0",
                started_at=started,
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            score = cur_score if day < 7 else prev_score
            tr = TaskResult(
                task_id="L0_001",
                suite="L0_smoke",
                model=model_name,
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


def test_regressions_down_finds_model_a():
    eng = _engine()
    with Session(eng) as session:
        _seed_two_models(session)
        panel = compute_regressions(
            session,
            window_days=7,
            min_delta=0.05,
            direction="down",
        )

    assert panel.direction == "down"
    assert panel.window_days == 7
    models = {item.model for item in panel.items}
    assert "model-a" in models
    assert "model-b" not in models

    a = next(item for item in panel.items if item.model == "model-a")
    assert a.tier == "T2"
    assert a.suite == "L0_smoke"
    assert a.score_now < a.score_prev
    assert a.delta_pct < -0.05
    assert a.n_now == 7
    assert a.n_prev == 7
    assert a.last_run_at is not None


def test_regressions_up_finds_model_b():
    eng = _engine()
    with Session(eng) as session:
        _seed_two_models(session)
        panel = compute_regressions(
            session,
            window_days=7,
            min_delta=0.05,
            direction="up",
        )

    models = {item.model for item in panel.items}
    assert "model-b" in models
    assert "model-a" not in models
    b = next(item for item in panel.items if item.model == "model-b")
    assert b.delta_pct > 0.05


def test_regressions_limit_caps_results():
    eng = _engine()
    with Session(eng) as session:
        _seed_two_models(session)
        panel = compute_regressions(
            session,
            window_days=7,
            min_delta=0.01,
            direction="down",
            limit=1,
        )
    assert len(panel.items) <= 1
