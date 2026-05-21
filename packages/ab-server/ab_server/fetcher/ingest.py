from __future__ import annotations

from collections.abc import Iterable

from sqlmodel import Session, select

from ab_server.fetcher.parser import ParsedRun
from ab_server.models import RegisteredRepo, Submission, TaskResult


def ingest_runs(
    session: Session,
    repo: RegisteredRepo,
    parsed_runs: Iterable[ParsedRun],
) -> tuple[int, int]:
    """Insert one Submission + one TaskResult per parsed run, idempotent."""
    inserted = 0
    skipped = 0
    for run in parsed_runs:
        existing = session.exec(
            select(Submission)
            .where(Submission.registered_repo_id == repo.id)
            .where(Submission.source_commit_sha == run.source_commit_sha)
            .where(Submission.source_path == run.source_path)
        ).first()
        if existing is not None:
            skipped += 1
            continue

        submission = Submission(
            registered_repo_id=repo.id,
            source_commit_sha=run.source_commit_sha,
            source_path=run.source_path,
            trust_tier="self_reported",
            model=run.model,
            tier=run.tier,
            dataset_version=run.dataset_version,
        )
        session.add(submission)
        session.commit()
        session.refresh(submission)

        suite = str(run.metadata.get("suite") or run.scores.get("suite") or _suite_from_task(run.task_id))
        score_total = float(run.scores.get("total_score") or 0.0)
        passed = bool(run.scores.get("pass"))
        status_value = "passed" if passed else "failed"

        task_result = TaskResult(
            submission_id=submission.id,
            task_id=run.task_id,
            suite=suite,
            model=run.model,
            tier=run.tier,
            tier_hash=str(run.metadata.get("tier_hash") or ""),
            status=status_value,
            score_total=score_total,
            cost_usd=float(run.metadata.get("cost_usd") or 0.0),
            latency_ms=int(run.metadata.get("latency_ms") or 0),
            trajectory_blob_ref=str(run.path / "trajectory.jsonl"),
        )
        session.add(task_result)
        session.commit()
        inserted += 1

    return inserted, skipped


def _suite_from_task(task_id: str) -> str:
    if "_" in task_id:
        return task_id.rsplit("_", 1)[0]
    return task_id
