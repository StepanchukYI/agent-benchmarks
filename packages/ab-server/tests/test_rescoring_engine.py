from __future__ import annotations

import json
from pathlib import Path

import pytest
from ab_server.models import (
    RegisteredRepo,
    ScorerVerdictRow,
    Submission,
    TaskResult,
    User,
)
from ab_server.rescoring import rescore_submission
from sqlmodel import Session, SQLModel, create_engine, select


def _write_passing_trajectory(traj_path: Path) -> None:
    events = [
        {
            "event": "run_start",
            "run_id": "r1",
            "task_id": "L0_001",
            "model": "claude-sonnet",
            "harness": "claude-code-cli@0.4.1",
            "tier": "T0",
            "tier_hash": "sha256:0",
            "dataset_version": "ab-datasets==0.0.1",
            "prompt_template_hash": None,
            "started_at": "2026-05-21T12:00:00Z",
        },
        {
            "event": "turn",
            "idx": 0,
            "role": "assistant",
            "tool_calls": [
                {"name": "write_file", "args": {"path": "notes/greeting.txt", "content": "Hello, Example.\n"}}
            ],
            "tool_returns": [{"path": "notes/greeting.txt", "content": "Hello, Example.\n"}],
            "model_output": "wrote file",
            "vault_state_diff": {"created": ["notes/greeting.txt"], "modified": [], "deleted": []},
            "tokens_in": 12,
            "tokens_out": 6,
            "latency_ms": 100,
            "cost_usd": 0.0,
        },
        {
            "event": "run_end",
            "finished_at": "2026-05-21T12:00:14Z",
            "status": "completed",
            "totals": {"tokens_in": 12, "tokens_out": 6, "latency_ms": 100, "cost_usd": 0.0, "score": 1.0},
        },
    ]
    traj_path.parent.mkdir(parents=True, exist_ok=True)
    with traj_path.open("w") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")


@pytest.fixture()
def session_factory(tmp_path: Path) -> Session:
    db_path = tmp_path / "test.db"
    engine = create_engine(f"sqlite:///{db_path}", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def _seed_submission(
    session: Session,
    *,
    fetcher_root: Path,
    self_total: float,
    repo_url: str = "https://github.com/alice/results",
) -> Submission:
    user = User(github_id="u1", handle="alice", avatar_url=None)
    session.add(user)
    session.commit()
    session.refresh(user)
    repo = RegisteredRepo(
        user_id=user.id,
        repo_url=repo_url,
        default_branch="main",
        is_public=True,
        status="registered",
    )
    session.add(repo)
    session.commit()
    session.refresh(repo)

    source_path = "results/20260521T000000Z-run-1"
    repo_clone = fetcher_root / str(repo.id)
    traj_path = repo_clone / source_path / "trajectory.jsonl"
    _write_passing_trajectory(traj_path)

    submission = Submission(
        registered_repo_id=repo.id,
        source_commit_sha="sha-1",
        source_path=source_path,
        trust_tier="self_reported",
        model="claude-sonnet",
        tier="T0",
        dataset_version="ab-datasets==0.0.1",
    )
    session.add(submission)
    session.commit()
    session.refresh(submission)

    task_result = TaskResult(
        submission_id=submission.id,
        task_id="L0_001",
        suite="file-ops",
        model="claude-sonnet",
        tier="T0",
        tier_hash="sha256:0",
        status="passed",
        score_total=self_total,
        cost_usd=0.0,
        latency_ms=100,
        trajectory_blob_ref=str(traj_path),
    )
    session.add(task_result)
    session.commit()

    return submission


def test_rescore_verified_when_self_matches_replay(
    tmp_path: Path,
    session_factory: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher_root = tmp_path / "cache"
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(fetcher_root))

    submission = _seed_submission(
        session_factory, fetcher_root=fetcher_root, self_total=1.0
    )

    report = rescore_submission(session_factory, submission)
    assert report.error is None, report.error
    assert report.trust_tier == "verified"
    assert report.discrepancy_pct < 0.01
    assert report.rescored_total == pytest.approx(1.0, abs=1e-6)

    session_factory.refresh(submission)
    assert submission.trust_tier == "verified"
    assert submission.re_scored_at is not None

    verdicts = session_factory.exec(select(ScorerVerdictRow)).all()
    assert len(verdicts) >= 1
    assert any(v.scorer_name == "file_diff" for v in verdicts)


def test_rescore_self_reported_when_discrepancy_large(
    tmp_path: Path,
    session_factory: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher_root = tmp_path / "cache"
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(fetcher_root))

    submission = _seed_submission(
        session_factory, fetcher_root=fetcher_root, self_total=0.4
    )

    report = rescore_submission(session_factory, submission)
    assert report.error is None, report.error
    assert report.trust_tier == "self_reported"
    assert report.discrepancy_pct > 0.5
    session_factory.refresh(submission)
    assert submission.trust_tier == "self_reported"
    assert submission.discrepancy_pct is not None
    assert submission.discrepancy_pct > 0.5


def test_rescore_failure_when_trajectory_missing(
    tmp_path: Path,
    session_factory: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fetcher_root = tmp_path / "cache"
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(fetcher_root))

    user = User(github_id="u1", handle="alice", avatar_url=None)
    session_factory.add(user)
    session_factory.commit()
    session_factory.refresh(user)
    repo = RegisteredRepo(
        user_id=user.id,
        repo_url="https://github.com/alice/results",
        default_branch="main",
        is_public=True,
        status="registered",
    )
    session_factory.add(repo)
    session_factory.commit()
    session_factory.refresh(repo)
    submission = Submission(
        registered_repo_id=repo.id,
        source_commit_sha="sha-1",
        source_path="results/missing",
        trust_tier="self_reported",
        model="claude-sonnet",
        tier="T0",
        dataset_version="ab-datasets==0.0.1",
    )
    session_factory.add(submission)
    session_factory.commit()
    session_factory.refresh(submission)

    report = rescore_submission(session_factory, submission)
    assert report.error is not None
    assert submission.trust_tier == "self_reported"
