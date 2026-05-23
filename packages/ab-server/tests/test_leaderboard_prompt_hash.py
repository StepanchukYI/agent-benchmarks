"""Prompt-as-row-identity: prompt_hash (= tier_hash) splits leaderboard rows.

Two task_results identical except for tier_hash must become two distinct rows —
this is the headline behavior (a custom CLAUDE.md at the same tier no longer
collapses into the vanilla row). Verifies LeaderboardRow surfaces prompt_hash +
prompt_label.
"""
from __future__ import annotations

from ab_server.leaderboard import compute_leaderboard_response
from ab_server.models import TaskResult
from sqlmodel import Session, SQLModel, create_engine


def _engine():
    eng = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(eng)
    return eng


def _task_result(task_id: str, tier_hash: str, prompt_label: str | None) -> TaskResult:
    return TaskResult(
        task_id=task_id,
        suite="L0_smoke",
        model="claude-haiku-4-5",
        tier="T0",
        tier_hash=tier_hash,
        status="passed",
        score_total=0.9,
        score_correctness=0.9,
        passed=True,
        harness="claude-code",
        effort="low",
        prompt_label=prompt_label,
    )


def test_distinct_prompt_hash_splits_rows() -> None:
    """Same (model, operator, tier, harness, effort), different tier_hash → 2 rows."""
    eng = _engine()
    with Session(eng) as session:
        session.add(_task_result("L0_001", "h" * 64, "karpathy-rules"))
        session.add(_task_result("L0_002", "v" * 64, None))
        session.commit()

        resp = compute_leaderboard_response(session)

    assert len(resp.rows) == 2
    by_hash = {r.prompt_hash: r for r in resp.rows}
    assert set(by_hash) == {"h" * 64, "v" * 64}
    assert by_hash["h" * 64].prompt_label == "karpathy-rules"
    assert by_hash["v" * 64].prompt_label is None
    # tier stays alongside prompt_hash (does not subsume it).
    assert all(r.tier == "T0" for r in resp.rows)


def test_same_prompt_hash_aggregates_one_row() -> None:
    """Two results sharing tier_hash → one row aggregating both."""
    eng = _engine()
    with Session(eng) as session:
        session.add(_task_result("L0_001", "h" * 64, "karpathy-rules"))
        session.add(_task_result("L0_002", "h" * 64, "karpathy-rules"))
        session.commit()

        resp = compute_leaderboard_response(session)

    assert len(resp.rows) == 1
    assert resp.rows[0].prompt_hash == "h" * 64
    assert resp.rows[0].prompt_label == "karpathy-rules"
    assert resp.rows[0].runs == 2


def test_empty_tier_hash_normalizes_to_null_prompt_hash() -> None:
    """Legacy rows with empty tier_hash → prompt_hash None, single bucket."""
    eng = _engine()
    with Session(eng) as session:
        session.add(_task_result("L0_001", "", None))
        session.add(_task_result("L0_002", "", None))
        session.commit()

        resp = compute_leaderboard_response(session)

    assert len(resp.rows) == 1
    assert resp.rows[0].prompt_hash is None
