from __future__ import annotations

from ab_server.leaderboard import compute_pareto
from ab_server.models import TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def test_pareto_frontier_flagged_correctly():
    # 4 models, all tier T2, mean-cost vs mean-score:
    #   cheap-good:  cost 0.01, score 0.9   <- frontier
    #   pricey-best: cost 0.10, score 0.95  <- frontier (higher score than cheap-good)
    #   midmid:      cost 0.05, score 0.7   <- dominated by cheap-good
    #   premium-bad: cost 0.20, score 0.6   <- dominated by everyone
    points = [
        ("cheap-good", 0.01, 0.9),
        ("pricey-best", 0.10, 0.95),
        ("midmid", 0.05, 0.7),
        ("premium-bad", 0.20, 0.6),
    ]
    eng = _engine()
    with Session(eng) as session:
        for model, cost, score in points:
            for _ in range(3):
                tr = TaskResult(
                    task_id="L0_001",
                    suite="L0_smoke",
                    model=model,
                    tier="T2",
                    tier_hash="sha256:abc",
                    status="completed",
                    score_total=score,
                    cost_usd=cost,
                    latency_ms=1000,
                )
                session.add(tr)
        session.commit()

        series = compute_pareto(session)

    by_model = {p.model: p for p in series.points}
    assert by_model["cheap-good"].on_frontier is True
    assert by_model["pricey-best"].on_frontier is True
    assert by_model["midmid"].on_frontier is False
    assert by_model["premium-bad"].on_frontier is False
    assert by_model["cheap-good"].cost_usd_mean < by_model["pricey-best"].cost_usd_mean


def test_pareto_filters_suites():
    eng = _engine()
    with Session(eng) as session:
        for suite, score in [("L0_smoke", 0.5), ("L1_smoke", 0.8)]:
            tr = TaskResult(
                task_id="L0_001",
                suite=suite,
                model="solo",
                tier="T2",
                tier_hash="sha256:abc",
                status="completed",
                score_total=score,
                cost_usd=0.01,
                latency_ms=1000,
            )
            session.add(tr)
        session.commit()
        series = compute_pareto(session, suites=["L1_smoke"])

    assert len(series.points) == 1
    assert series.points[0].score_mean == 0.8
