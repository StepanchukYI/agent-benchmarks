"""Tests for pillar_counts on LeaderboardRow (B3).

pillar_counts is index-aligned to the `scores` / `PILLARS` order:
  [correctness, context_eff, tool_skill, memory, latency]
Each value is the count of task-results that contributed a non-null score
to that pillar — i.e. len(bucket_pillars[k]).
"""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.leaderboard.queries import compute_leaderboard_response
from ab_server.main import app
from ab_server.models import TaskResult
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def db_engine(tmp_path: Path) -> Iterator[object]:
    db_path = tmp_path / "pillar_counts.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    def _override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def _make_tr(
    session: Session,
    *,
    model: str,
    score_correctness: float | None = None,
    score_context_eff: float | None = None,
    score_tool_skill: float | None = None,
    score_memory: float | None = None,
    score_latency: float | None = None,
) -> None:
    """Insert a TaskResult with fine-grained per-pillar control."""
    tr = TaskResult(
        task_id="L0_001",
        suite="L0_smoke",
        model=model,
        tier="T0",
        tier_hash="abc",
        status="completed",
        score_total=0.5,
        score_correctness=score_correctness,
        score_context_eff=score_context_eff,
        score_tool_skill=score_tool_skill,
        score_memory=score_memory,
        score_latency=score_latency,
    )
    session.add(tr)
    session.commit()


def test_pillar_counts_differing_contributions(db_engine: object) -> None:
    """pillar_counts reflects actual per-pillar contribution counts.

    Setup: 3 task-results for model "m1".
      row 0: correctness=0.9, context_eff=0.8, tool_skill=0.7, memory=None, latency=None
      row 1: correctness=0.8, context_eff=None, tool_skill=0.6, memory=0.5, latency=None
      row 2: correctness=0.7, context_eff=None, tool_skill=None, memory=None, latency=0.4

    Expected pillar_counts (order: correctness, context_eff, tool_skill, memory, latency):
      [3, 1, 2, 1, 1]
    """
    with Session(db_engine) as session:
        _make_tr(session, model="m1",
                 score_correctness=0.9, score_context_eff=0.8, score_tool_skill=0.7)
        _make_tr(session, model="m1",
                 score_correctness=0.8, score_tool_skill=0.6, score_memory=0.5)
        _make_tr(session, model="m1",
                 score_correctness=0.7, score_latency=0.4)

        result = compute_leaderboard_response(session)

    assert len(result.rows) == 1
    row = result.rows[0]
    assert len(row.pillar_counts) == 5, "pillar_counts must have 5 entries (one per pillar)"
    # index 0 = correctness: all 3 rows
    assert row.pillar_counts[0] == 3
    # index 1 = context_eff: only row 0
    assert row.pillar_counts[1] == 1
    # index 2 = tool_skill: rows 0 and 1
    assert row.pillar_counts[2] == 2
    # index 3 = memory: only row 1
    assert row.pillar_counts[3] == 1
    # index 4 = latency: only row 2
    assert row.pillar_counts[4] == 1


def test_pillar_counts_all_null_pillar(db_engine: object) -> None:
    """A pillar with no contributions at all yields count=0 (not missing)."""
    with Session(db_engine) as session:
        # Only correctness measured; all other pillars absent.
        _make_tr(session, model="m1", score_correctness=0.9)
        _make_tr(session, model="m1", score_correctness=0.8)

        result = compute_leaderboard_response(session)

    row = result.rows[0]
    assert row.pillar_counts[0] == 2  # correctness: 2 rows
    assert row.pillar_counts[1] == 0  # context_eff: none
    assert row.pillar_counts[2] == 0  # tool_skill: none
    assert row.pillar_counts[3] == 0  # memory: none
    assert row.pillar_counts[4] == 0  # latency: none


def test_pillar_counts_aligned_to_scores(db_engine: object) -> None:
    """pillar_counts[i] > 0 iff scores[i] is not None (index alignment check)."""
    with Session(db_engine) as session:
        _make_tr(session, model="m1",
                 score_correctness=0.9, score_tool_skill=0.7)

        result = compute_leaderboard_response(session)

    row = result.rows[0]
    for i, (score, count) in enumerate(zip(row.scores, row.pillar_counts, strict=True)):
        if score is not None:
            assert count > 0, f"pillar {i}: score is not None but count is 0"
        else:
            assert count == 0, f"pillar {i}: score is None but count is {count}"
