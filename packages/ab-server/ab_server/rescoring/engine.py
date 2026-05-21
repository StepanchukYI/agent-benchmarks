from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

from ab_datasets.loaders import load_task
from ab_datasets.schemas import ScorerVerdict, Task, TrustTier
from ab_harness.scorers.runner import run_scorer_chain
from sqlmodel import Session, select

from ab_server.config import Settings
from ab_server.models import RegisteredRepo, ScorerVerdictRow, Submission, TaskResult

_log = logging.getLogger(__name__)

_VERIFIED_THRESHOLD = 0.01
# Below this self-reported total, use absolute (not relative) discrepancy.
# Avoids div-by-near-zero when a model reports total_score = 0 — otherwise
# any tiny rescored total inflates the relative discrepancy past the gate
# and "all-zero matches all-zero" can never reach the verified tier.
_RELATIVE_FLOOR = 0.01


@dataclass
class RescoreReport:
    submission_id: str
    trust_tier: str
    self_total: float
    rescored_total: float
    discrepancy_pct: float
    verdicts: list[ScorerVerdict] = field(default_factory=list)
    error: str | None = None


def rescore_submission(session: Session, submission: Submission) -> RescoreReport:
    settings = Settings()
    repo = session.get(RegisteredRepo, submission.registered_repo_id)
    if repo is None:
        return _failure(submission, "registered_repo missing")

    clone_dir = Path(settings.fetcher_cache_dir) / str(repo.id)
    clone_dir_resolved = clone_dir.resolve()
    candidate = (clone_dir / submission.source_path / "trajectory.jsonl").resolve()
    try:
        candidate.relative_to(clone_dir_resolved)
    except ValueError:
        return _failure(
            submission,
            f"source_path escapes clone dir: {submission.source_path!r}",
        )
    traj_path = candidate
    if not traj_path.exists():
        return _failure(submission, f"trajectory not found at {traj_path}")

    task_id = _task_id_for_submission(session, submission)
    if not task_id:
        return _failure(submission, "task_id not resolvable")

    task = _find_task(task_id, settings.datasets_root)
    if task is None:
        return _failure(submission, f"task yaml not found for {task_id}")

    self_total = _self_reported_total(submission, session)

    try:
        verdicts = run_scorer_chain(task, traj_path, workdir=None, mode="replay")
    except Exception as exc:
        _log.exception("scorer chain raised")
        return _failure(submission, f"scorer chain raised: {exc}")

    has_unsupported = _has_replay_unsupported(verdicts)
    rescored_total = _verdict_mean(verdicts)
    if self_total < _RELATIVE_FLOOR:
        # Absolute scale: score axis is 0-1, so 0.01 absolute == 1% relative.
        discrepancy = abs(rescored_total - self_total)
    else:
        discrepancy = abs(rescored_total - self_total) / self_total

    new_tier = _decide_tier(
        task,
        discrepancy=discrepancy,
        has_unsupported=has_unsupported,
    )

    submission.trust_tier = new_tier
    submission.re_scored_at = datetime.now(UTC)
    submission.discrepancy_pct = discrepancy
    session.add(submission)
    session.commit()
    session.refresh(submission)

    _persist_verdicts(session, submission, verdicts)

    return RescoreReport(
        submission_id=str(submission.id),
        trust_tier=new_tier,
        self_total=self_total,
        rescored_total=rescored_total,
        discrepancy_pct=discrepancy,
        verdicts=verdicts,
    )


def _failure(submission: Submission, reason: str) -> RescoreReport:
    return RescoreReport(
        submission_id=str(submission.id),
        trust_tier=submission.trust_tier,
        self_total=0.0,
        rescored_total=0.0,
        discrepancy_pct=0.0,
        verdicts=[],
        error=reason,
    )


def _task_id_for_submission(session: Session, submission: Submission) -> str | None:
    result = session.exec(
        select(TaskResult).where(TaskResult.submission_id == submission.id)
    ).first()
    return result.task_id if result else None


def _find_task(task_id: str, datasets_root: str) -> Task | None:
    roots: list[Path] = []
    if datasets_root:
        roots.append(Path(datasets_root))
    try:
        import ab_datasets

        roots.append(Path(ab_datasets.__file__).resolve().parent)
    except ImportError:
        pass

    for root in roots:
        if not root.exists():
            continue
        for candidate in root.rglob(f"{task_id}*.yaml"):
            try:
                task = load_task(candidate)
            except Exception:
                continue
            if task.id == task_id:
                return task
    return None


def _self_reported_total(submission: Submission, session: Session) -> float:
    result = session.exec(
        select(TaskResult).where(TaskResult.submission_id == submission.id)
    ).first()
    return float(result.score_total) if result else 0.0


def _has_replay_unsupported(verdicts: list[ScorerVerdict]) -> bool:
    for v in verdicts:
        detail = v.detail if isinstance(v.detail, dict) else {}
        if detail.get("replay_unsupported"):
            return True
    return False


def _verdict_mean(verdicts: list[ScorerVerdict]) -> float:
    if not verdicts:
        return 0.0
    return float(fmean(v.score for v in verdicts))


def _decide_tier(
    task: Task,
    *,
    discrepancy: float,
    has_unsupported: bool,
) -> str:
    ceiling = task.trust_tier_ceiling
    if has_unsupported:
        return "self_reported"
    if discrepancy < _VERIFIED_THRESHOLD:
        if ceiling == TrustTier.self_reported:
            return "self_reported"
        return "verified"
    return "self_reported"


def _persist_verdicts(
    session: Session,
    submission: Submission,
    verdicts: list[ScorerVerdict],
) -> None:
    task_result = session.exec(
        select(TaskResult).where(TaskResult.submission_id == submission.id)
    ).first()
    if task_result is None:
        return

    existing = session.exec(
        select(ScorerVerdictRow).where(ScorerVerdictRow.task_result_id == task_result.id)
    ).all()
    for row in existing:
        session.delete(row)
    session.commit()

    for verdict in verdicts:
        detail: Any = verdict.detail
        if isinstance(detail, str):
            detail = {"text": detail}
        row = ScorerVerdictRow(
            task_result_id=task_result.id,
            scorer_name=verdict.scorer_name,
            kind=str(verdict.kind),
            pass_=verdict.pass_,
            score=verdict.score,
            detail=detail or {},
        )
        session.add(row)
    session.commit()
