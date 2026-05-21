from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ab_server.leaderboard import compute_matrix
from ab_server.models import Run, TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _seed_pillars(session: Session) -> None:
    now = datetime.now(UTC)
    for day in range(14):
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
        # current window (day 0..6) score 0.80; previous window (7..13) score 0.60.
        base = 0.80 if day < 7 else 0.60
        tr = TaskResult(
            task_id="L0_001",
            suite="L0_smoke",
            model="claude-sonnet-4-5",
            tier="T2",
            tier_hash="sha256:abc",
            status="completed",
            score_correctness=base + 0.05,
            score_context_eff=base - 0.05,
            score_tool_skill=base,
            score_memory=base + 0.01,
            score_latency=base - 0.01,
            score_total=base,
            cost_usd=0.02,
            latency_ms=1000,
            run_id=run.id,
        )
        session.add(tr)
    session.commit()


def test_cell_has_pillar_means_and_sparkline():
    eng = _engine()
    with Session(eng) as session:
        _seed_pillars(session)
        matrix = compute_matrix(session)

    assert len(matrix.rows) == 1
    row = matrix.rows[0]
    cell = row.cells["L0_smoke"]

    assert cell.score_correctness is not None
    assert cell.score_context_eff is not None
    assert cell.score_tool_skill is not None
    assert cell.score_memory is not None
    assert cell.score_latency is not None

    # all 14 entries flow into the overall mean
    assert cell.n == 14
    # current-window pillar mean reflects mixed days 0..13 in score_correctness.
    assert 0.6 < cell.score_correctness < 0.9

    assert isinstance(cell.sparkline_7d, list)
    assert 0 < len(cell.sparkline_7d) <= 7
    for value in cell.sparkline_7d:
        assert isinstance(value, float)

    assert cell.previous_mean is not None
    assert cell.delta is not None
    # current (0.80) > previous (0.60)
    assert cell.delta > 0


def test_cell_pillars_none_when_no_data():
    eng = _engine()
    with Session(eng) as session:
        tr = TaskResult(
            task_id="L0_001",
            suite="L0_smoke",
            model="m",
            tier="T0",
            tier_hash="sha256:abc",
            status="completed",
            score_correctness=0.0,
            score_context_eff=0.0,
            score_tool_skill=0.0,
            score_memory=0.0,
            score_latency=0.0,
            score_total=0.5,
            cost_usd=0.0,
            latency_ms=0,
        )
        session.add(tr)
        session.commit()
        matrix = compute_matrix(session)

    cell = matrix.rows[0].cells["L0_smoke"]
    # Pillars default to 0.0 in DB, so they aggregate to 0.0 (not None).
    assert cell.score_correctness == 0.0
    # No prior window, no previous_mean.
    assert cell.previous_mean is None
    assert cell.delta is None
