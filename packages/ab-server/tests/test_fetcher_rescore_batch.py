"""M_F: sync_repo must cap inline rescoring per call.

We pre-seed 20 unscored Submissions for one repo, stub out the git clone
and the rescore engine (we're testing the loop bound, not the engine),
then assert sync_repo only rescores `sync_rescore_batch_size` submissions
in one call.
"""
from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from ab_server.fetcher import worker as worker_module
from ab_server.fetcher.worker import sync_repo
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from sqlmodel import Session, SQLModel, create_engine, select


@pytest.fixture()
def session(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Session]:
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(tmp_path / "cache"))
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


@pytest.fixture()
def repo(session: Session, tmp_path: Path) -> RegisteredRepo:
    user = User(github_id="u1", handle="alice", avatar_url=None)
    session.add(user)
    session.commit()
    session.refresh(user)
    r = RegisteredRepo(
        user_id=user.id,
        repo_url="https://github.com/alice/results",
        default_branch="main",
        is_public=True,
        status="registered",
        sync_cursor="old-sha",
    )
    session.add(r)
    session.commit()
    session.refresh(r)

    # Make sure the (would-be) clone dir exists so the worker doesn't trip
    # over a missing path. We're not actually cloning anything.
    cache_root = Path(tmp_path / "cache")
    (cache_root / str(r.id)).mkdir(parents=True, exist_ok=True)
    return r


def _seed_submissions(session: Session, repo: RegisteredRepo, n: int) -> list[Submission]:
    """Create n unscored submissions with strictly increasing ingested_at."""
    base = datetime(2026, 5, 21, 12, 0, 0, tzinfo=UTC)
    subs: list[Submission] = []
    for i in range(n):
        sub = Submission(
            registered_repo_id=repo.id,
            source_commit_sha=f"sha-{i:02d}",
            source_path=f"results/run-{i:02d}",
            trust_tier="self_reported",
            model="claude-sonnet",
            tier="T0",
            dataset_version="ab-datasets==0.0.1",
            ingested_at=base + timedelta(minutes=i),
        )
        session.add(sub)
        session.commit()
        session.refresh(sub)
        # Add a matching TaskResult so the rescore engine could resolve the
        # task_id if it were ever invoked (it won't be — we stub it out).
        session.add(
            TaskResult(
                submission_id=sub.id,
                task_id="L0_001",
                suite="L0_smoke",
                model="claude-sonnet",
                tier="T0",
                tier_hash="",
                status="passed",
                score_total=1.0,
            )
        )
        session.commit()
        subs.append(sub)
    return subs


def test_sync_repo_caps_rescore_loop_at_batch_size(
    session: Session,
    repo: RegisteredRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_submissions(session, repo, 20)

    # Stub clone_or_pull → returns a "new" head sha so we don't early-return
    # on the unchanged-cursor branch.
    monkeypatch.setattr(
        worker_module, "clone_or_pull", lambda url, branch, dest: "new-head-sha"
    )

    # Stub the rescore engine: count calls + mark submission scored so the
    # second sync sees them as completed (and we test eventual consistency).
    call_count = {"n": 0}

    from ab_server.rescoring.engine import RescoreReport

    def _fake_rescore(sess: Session, submission: Submission) -> RescoreReport:
        call_count["n"] += 1
        submission.re_scored_at = datetime.now(UTC)
        sess.add(submission)
        sess.commit()
        return RescoreReport(
            submission_id=str(submission.id),
            trust_tier="verified",
            self_total=1.0,
            rescored_total=1.0,
            discrepancy_pct=0.0,
            verdicts=[],
        )

    # Patch at the rescoring package level — worker.py does a local import.
    import ab_server.rescoring as rescoring_pkg

    monkeypatch.setattr(rescoring_pkg, "rescore_submission", _fake_rescore)

    report = sync_repo(session, repo)
    # Default batch size is 5 (see Settings.sync_rescore_batch_size).
    assert report.rescored == 5
    assert call_count["n"] == 5

    # 15 still unscored. Reset the call counter, run again — should rescore
    # the next 5 (eventually consistent across syncs).
    call_count["n"] = 0
    second = sync_repo(session, repo)
    assert second.rescored == 5
    assert call_count["n"] == 5

    unscored = session.exec(
        select(Submission)
        .where(Submission.registered_repo_id == repo.id)
        .where(Submission.re_scored_at.is_(None))
    ).all()
    assert len(unscored) == 10


def test_sync_repo_picks_newest_first(
    session: Session,
    repo: RegisteredRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Newest ingested submissions must be rescored before older ones."""
    subs = _seed_submissions(session, repo, 8)
    # subs are returned in insertion order = ingested_at ascending.
    # The newest 5 should be rescored first.
    expected_first = {str(s.id) for s in subs[3:]}

    monkeypatch.setattr(
        worker_module, "clone_or_pull", lambda url, branch, dest: "new-head"
    )

    rescored_ids: list[str] = []

    from ab_server.rescoring.engine import RescoreReport

    def _fake_rescore(sess: Session, submission: Submission) -> RescoreReport:
        rescored_ids.append(str(submission.id))
        submission.re_scored_at = datetime.now(UTC)
        sess.add(submission)
        sess.commit()
        return RescoreReport(
            submission_id=str(submission.id),
            trust_tier="verified",
            self_total=1.0,
            rescored_total=1.0,
            discrepancy_pct=0.0,
            verdicts=[],
        )

    import ab_server.rescoring as rescoring_pkg

    monkeypatch.setattr(rescoring_pkg, "rescore_submission", _fake_rescore)

    sync_repo(session, repo)
    assert set(rescored_ids) == expected_first


def test_sync_repo_respects_custom_batch_size(
    session: Session,
    repo: RegisteredRepo,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Settings.sync_rescore_batch_size is the cap, not a constant."""
    _seed_submissions(session, repo, 20)

    monkeypatch.setenv("SYNC_RESCORE_BATCH_SIZE", "3")
    monkeypatch.setattr(
        worker_module, "clone_or_pull", lambda url, branch, dest: "new-head"
    )

    from ab_server.rescoring.engine import RescoreReport

    def _fake_rescore(sess: Session, submission: Submission) -> RescoreReport:
        submission.re_scored_at = datetime.now(UTC)
        sess.add(submission)
        sess.commit()
        return RescoreReport(
            submission_id=str(submission.id),
            trust_tier="verified",
            self_total=1.0,
            rescored_total=1.0,
            discrepancy_pct=0.0,
            verdicts=[],
        )

    import ab_server.rescoring as rescoring_pkg

    monkeypatch.setattr(rescoring_pkg, "rescore_submission", _fake_rescore)

    report = sync_repo(session, repo)
    assert report.rescored == 3
