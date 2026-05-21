from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from sqlmodel import Session, select

from ab_server.config import Settings
from ab_server.fetcher.git import clone_or_pull
from ab_server.fetcher.ingest import ingest_runs
from ab_server.fetcher.parser import iter_parsed_runs
from ab_server.models import RegisteredRepo, Submission

_log = logging.getLogger(__name__)


@dataclass
class SyncReport:
    repo_id: str
    commit_sha: str | None
    inserted: int
    skipped: int
    rescored: int
    errors: list[str] = field(default_factory=list)


def sync_repo(session: Session, repo: RegisteredRepo) -> SyncReport:
    settings = Settings()
    cache_root = Path(settings.fetcher_cache_dir)
    dest = cache_root / str(repo.id)

    report = SyncReport(
        repo_id=str(repo.id), commit_sha=None, inserted=0, skipped=0, rescored=0
    )

    try:
        head_sha = clone_or_pull(repo.repo_url, repo.default_branch, dest)
    except Exception as exc:
        report.errors.append(f"clone_or_pull failed: {exc}")
        return report

    report.commit_sha = head_sha
    if repo.sync_cursor == head_sha:
        repo.last_synced_at = datetime.now(UTC)
        session.add(repo)
        session.commit()
        return report

    parsed_runs = list(iter_parsed_runs(dest, head_sha))
    inserted, skipped = ingest_runs(session, repo, parsed_runs)
    report.inserted = inserted
    report.skipped = skipped

    if inserted:
        from ab_server.rescoring import rescore_submission

        new_submissions = session.exec(
            select(Submission)
            .where(Submission.registered_repo_id == repo.id)
            .where(Submission.source_commit_sha == head_sha)
        ).all()
        for submission in new_submissions:
            try:
                result = rescore_submission(session, submission)
                report.rescored += 1
                if result.error:
                    report.errors.append(f"rescore {submission.id}: {result.error}")
            except Exception as exc:
                _log.exception("rescore failed")
                report.errors.append(f"rescore {submission.id}: {exc}")

    repo.last_synced_at = datetime.now(UTC)
    repo.sync_cursor = head_sha
    session.add(repo)
    session.commit()
    return report
