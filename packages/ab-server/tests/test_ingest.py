from __future__ import annotations

import json
from pathlib import Path

import pytest
from ab_server.fetcher.ingest import ingest_runs
from ab_server.fetcher.parser import iter_parsed_runs
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from sqlmodel import Session, SQLModel, create_engine, select


def _write_run(run_dir: Path, run_id: str, task_id: str) -> None:
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task_id}\nmodel: claude-sonnet\ntier: T0\nsuite: file-ops\ndataset_version: 0.0.1\nharness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    (run_dir / "scores.json").write_text(
        json.dumps({
            "run_id": run_id,
            "task_id": task_id,
            "total_score": 0.95,
            "pass": True,
            "per_pillar": {
                "correctness": 0.9,
                "context_efficiency": 0.8,
                "tool_skill": 0.7,
                "memory_specific": 0.6,
                "latency_cost": 0.5,
            },
        }) + "\n"
    )
    (run_dir / "trajectory.jsonl").write_text("{}\n")


@pytest.fixture()
def session(tmp_path: Path) -> Session:
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def repo(session: Session) -> RegisteredRepo:
    user = User(github_id="u1", handle="alice", avatar_url=None)
    session.add(user)
    session.commit()
    session.refresh(user)
    repo = RegisteredRepo(
        user_id=user.id,
        repo_url="https://github.com/alice/results",
        default_branch="main",
        is_public=True,
        status="registered",
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)
    return repo


def test_ingest_inserts_submissions_and_task_results(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run(clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001")
    _write_run(clone / "results" / "20260521T000100Z-run-2", "run-2", "L0_002")

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted, skipped = ingest_runs(session, repo, parsed)

    assert inserted == 2
    assert skipped == 0

    subs = session.exec(select(Submission)).all()
    assert len(subs) == 2
    trs = session.exec(select(TaskResult)).all()
    assert len(trs) == 2
    assert {tr.task_id for tr in trs} == {"L0_001", "L0_002"}
    assert all(tr.suite == "file-ops" for tr in trs)
    # Per-pillar scores must be propagated from scores.json["per_pillar"].
    # Regression guard: ingest used to only set score_total, leaving every
    # pillar column at the 0.0 default → leaderboard rendered all pillars
    # as 0.0% even for high-scoring submissions.
    for tr in trs:
        assert tr.score_correctness == 0.9
        assert tr.score_context_eff == 0.8
        assert tr.score_tool_skill == 0.7
        assert tr.score_memory == 0.6
        assert tr.score_latency == 0.5
        assert tr.score_total == 0.95


def _write_run_with_trajectory(
    run_dir: Path, run_id: str, task_id: str, traj_lines: list[dict]
) -> None:
    _write_run(run_dir, run_id, task_id)
    (run_dir / "trajectory.jsonl").write_text(
        "".join(json.dumps(ev) + "\n" for ev in traj_lines)
    )


def test_ingest_populates_tokens_and_turns_from_run_end_totals(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    traj = [
        {"event": "run_start", "run_id": "run-1", "task_id": "L0_001"},
        {"event": "turn", "idx": 0, "role": "user", "tokens_in": 100, "tokens_out": 0},
        {"event": "turn", "idx": 1, "role": "assistant", "tokens_in": 0, "tokens_out": 200},
        {"event": "turn", "idx": 2, "role": "assistant", "tokens_in": 0, "tokens_out": 150},
        {
            "event": "run_end",
            "status": "completed",
            "totals": {"tokens_in": 100, "tokens_out": 350},
        },
    ]
    _write_run_with_trajectory(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", traj
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted, _ = ingest_runs(session, repo, parsed)
    assert inserted == 1

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    # run_end totals are authoritative.
    assert tr.tokens_in == 100
    assert tr.tokens_out == 350
    assert tr.tokens_total == 450
    # turns_total counts assistant turns only.
    assert tr.turns_total == 2


def test_ingest_falls_back_to_per_turn_tokens_without_totals(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    traj = [
        {"event": "run_start", "run_id": "run-1", "task_id": "L0_001"},
        {"event": "turn", "idx": 0, "role": "user", "tokens_in": 40, "tokens_out": 0},
        {"event": "turn", "idx": 1, "role": "assistant", "tokens_in": 0, "tokens_out": 60},
        {"event": "run_end", "status": "completed"},
    ]
    _write_run_with_trajectory(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", traj
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.tokens_total == 100
    assert tr.turns_total == 1


def _write_run_partial_pillars(run_dir: Path, run_id: str, task_id: str) -> None:
    """A run whose scores.json carries only correctness + a genuine 0.0 latency;
    the other three pillar keys are ABSENT from per_pillar."""
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task_id}\nmodel: claude-sonnet\ntier: T0\nsuite: file-ops\ndataset_version: 0.0.1\nharness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    (run_dir / "scores.json").write_text(
        json.dumps({
            "run_id": run_id,
            "task_id": task_id,
            "total_score": 0.9,
            "pass": True,
            # context_efficiency / tool_skill / memory_specific keys ABSENT.
            "per_pillar": {"correctness": 0.9, "latency_cost": 0.0},
        }) + "\n"
    )
    (run_dir / "trajectory.jsonl").write_text("{}\n")


def test_ingest_writes_none_for_absent_pillar_and_keeps_genuine_zero(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run_partial_pillars(clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001")

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    # Measured pillars keep their value — including a genuine 0.0.
    assert tr.score_correctness == 0.9
    assert tr.score_latency == 0.0
    # Absent pillars become None (not measured), NOT a phantom 0.0.
    assert tr.score_context_eff is None
    assert tr.score_tool_skill is None
    assert tr.score_memory is None


def _write_run_with_verdicts(
    run_dir: Path,
    run_id: str,
    task_id: str,
    verdicts: list[dict],
) -> None:
    """Write a run dir whose scores.json["verdicts"] is the supplied list."""
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        f"run_id: {run_id}\ntask_id: {task_id}\nmodel: claude-sonnet\ntier: T0\nsuite: file-ops\ndataset_version: 0.0.1\nharness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    (run_dir / "scores.json").write_text(
        json.dumps({
            "run_id": run_id,
            "task_id": task_id,
            "total_score": 0.5,
            "pass": all(v.get("pass", False) for v in verdicts) if verdicts else False,
            "per_pillar": {"correctness": 0.5},
            "verdicts": verdicts,
        }) + "\n"
    )
    (run_dir / "trajectory.jsonl").write_text("{}\n")


def test_ingest_passed_all_pass(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """passed=True when every decided scorer passes."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    verdicts = [
        {"scorer_name": "schema", "kind": "schema", "pass": True, "score": 1.0, "detail": {}},
        {"scorer_name": "file_diff", "kind": "deterministic", "pass": True, "score": 1.0, "detail": {}},
    ]
    _write_run_with_verdicts(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", verdicts
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.passed is True


def test_ingest_passed_one_fail(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """passed=False when at least one decided scorer fails."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    verdicts = [
        {"scorer_name": "schema", "kind": "schema", "pass": True, "score": 1.0, "detail": {}},
        {"scorer_name": "file_diff", "kind": "deterministic", "pass": False, "score": 0.0, "detail": {}},
    ]
    _write_run_with_verdicts(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", verdicts
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.passed is False


def test_ingest_passed_no_decided_verdicts(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    """passed=None when verdicts list is empty (zero decided scorers)."""
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run_with_verdicts(
        clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001", []
    )

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    ingest_runs(session, repo, parsed)

    tr = session.exec(select(TaskResult)).first()
    assert tr is not None
    assert tr.passed is None


def test_ingest_idempotent_second_call(
    tmp_path: Path, session: Session, repo: RegisteredRepo
) -> None:
    clone = tmp_path / "clone"
    (clone / "results").mkdir(parents=True)
    _write_run(clone / "results" / "20260521T000000Z-run-1", "run-1", "L0_001")
    _write_run(clone / "results" / "20260521T000100Z-run-2", "run-2", "L0_002")

    parsed = list(iter_parsed_runs(clone, source_commit_sha="sha1"))
    inserted1, skipped1 = ingest_runs(session, repo, parsed)
    inserted2, skipped2 = ingest_runs(session, repo, parsed)

    assert (inserted1, skipped1) == (2, 0)
    assert (inserted2, skipped2) == (0, 2)
    subs = session.exec(select(Submission)).all()
    assert len(subs) == 2
