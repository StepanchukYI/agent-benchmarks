from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ab_server.leaderboard import compute_heatmap, compute_pareto_history
from ab_server.models import Run, TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _tr(**kw) -> TaskResult:
    base = dict(
        task_id="L0_001",
        suite="L0_smoke",
        model="m",
        tier="T0",
        tier_hash="sha256:abc",
        status="completed",
        score_total=0.8,
        score_correctness=0.8,
        cost_usd=0.01,
        latency_ms=1000,
    )
    base.update(kw)
    return TaskResult(**base)


# ---- heatmap ----


def test_heatmap_groups_by_model_tier_suite():
    eng = _engine()
    with Session(eng) as session:
        # model-a × L0 = mean correctness 0.6; model-a × L1 = 0.9
        session.add(_tr(model="a", suite="L0_smoke", score_correctness=0.5))
        session.add(_tr(model="a", suite="L0_smoke", score_correctness=0.7))
        session.add(_tr(model="a", suite="L1_smoke", score_correctness=0.9))
        # model-b × L0 = 0.4
        session.add(_tr(model="b", suite="L0_smoke", score_correctness=0.4))
        session.commit()

        resp = compute_heatmap(session)

    assert resp.suites == ["L0_smoke", "L1_smoke"]
    by_model = {(r.model, r.tier): r for r in resp.rows}
    a = by_model[("a", "T0")]
    assert a.cells["L0_smoke"].score_correctness == 0.6
    assert a.cells["L0_smoke"].n == 2
    assert a.cells["L1_smoke"].score_correctness == 0.9
    assert a.cells["L1_smoke"].n == 1
    b = by_model[("b", "T0")]
    assert b.cells["L0_smoke"].score_correctness == 0.4
    assert "L1_smoke" not in b.cells


def test_heatmap_empty_db_returns_empty():
    eng = _engine()
    with Session(eng) as session:
        resp = compute_heatmap(session)
    assert resp.rows == []
    assert resp.suites == []


def test_heatmap_filters_suites():
    eng = _engine()
    with Session(eng) as session:
        session.add(_tr(suite="L0_smoke", score_correctness=0.5))
        session.add(_tr(suite="L1_smoke", score_correctness=0.9))
        session.commit()
        resp = compute_heatmap(session, suites=["L1_smoke"])
    assert resp.suites == ["L1_smoke"]
    assert len(resp.rows) == 1
    assert resp.rows[0].cells["L1_smoke"].score_correctness == 0.9


# ---- pareto history ----


def test_pareto_history_buckets_by_week():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        # Two runs ~2 weeks apart for the same model, each anchored via Run.
        for offset_days, cost, score in [(2, 0.10, 0.7), (12, 0.04, 0.9)]:
            run = Run(
                tenant_id="t",
                suite="L0_smoke",
                model="m",
                tier="T0",
                tier_hash="",
                dataset_version="v1",
                status="completed",
                started_at=now - timedelta(days=offset_days),
            )
            session.add(run)
            session.commit()
            session.refresh(run)
            session.add(
                _tr(run_id=run.id, cost_usd=cost, score_total=score)
            )
        session.commit()

        resp = compute_pareto_history(session, window_days=30)

    assert resp.window_days == 30
    assert len(resp.series) == 1
    item = resp.series[0]
    assert item.model == "m"
    assert item.tier == "T0"
    # Two distinct ISO-week buckets, sorted ascending by timestamp.
    assert len(item.history) == 2
    assert item.history[0].at <= item.history[1].at
    earliest, latest = item.history[0], item.history[1]
    assert latest.score_mean == 0.7  # the 2-day-ago run is the most recent week
    assert earliest.score_mean == 0.9
    assert latest.n == 1


def test_pareto_history_empty_db_returns_empty():
    eng = _engine()
    with Session(eng) as session:
        resp = compute_pareto_history(session, window_days=30)
    assert resp.series == []
    assert resp.window_days == 30


def test_pareto_history_window_zero_returns_empty():
    eng = _engine()
    with Session(eng) as session:
        session.add(_tr())
        session.commit()
        resp = compute_pareto_history(session, window_days=0)
    assert resp.series == []
    assert resp.window_days == 0


def test_pareto_history_excludes_outside_window():
    eng = _engine()
    now = datetime.now(UTC)
    with Session(eng) as session:
        old_run = Run(
            tenant_id="t",
            suite="L0_smoke",
            model="m",
            tier="T0",
            tier_hash="",
            dataset_version="v1",
            status="completed",
            started_at=now - timedelta(days=40),
        )
        session.add(old_run)
        session.commit()
        session.refresh(old_run)
        session.add(_tr(run_id=old_run.id))
        session.commit()
        resp = compute_pareto_history(session, window_days=30)
    assert resp.series == []
