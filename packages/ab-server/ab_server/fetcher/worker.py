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

    # Skip parse + ingest when upstream HEAD hasn't moved, but still fall
    # through to the rescore-stragglers pass below so submissions left
    # unscored by a previous capped sync get picked up on the next call.
    if repo.sync_cursor != head_sha:
        parsed_runs = list(iter_parsed_runs(dest, head_sha))
        inserted, skipped = ingest_runs(session, repo, parsed_runs)
        report.inserted = inserted
        report.skipped = skipped

    # Cap rescoring per sync (M_F). /repos/{id}/sync is a synchronous
    # request handler; rescoring N submissions in a tight loop holds the
    # worker for N * rescore_time. A repo that ships dozens of submissions
    # in one push would otherwise park a gunicorn worker until done.
    #
    # Trade-off: leftover submissions are picked up on subsequent syncs
    # (the fetcher cron + manual /sync). Worst-case latency to "fully
    # rescored" is roughly ceil(N / batch_size) * fetch_interval_sec.
    # Pick the newest unscored submissions first so the leaderboard
    # surfaces the freshest results soonest.
    from ab_server.rescoring import rescore_submission

    batch_size = max(1, settings.sync_rescore_batch_size)
    pending = session.exec(
        select(Submission)
        .where(Submission.registered_repo_id == repo.id)
        .where(Submission.re_scored_at.is_(None))
        .order_by(Submission.ingested_at.desc())
        .limit(batch_size)
    ).all()
    for submission in pending:
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
