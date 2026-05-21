"""Leaderboard aggregation queries.

All three public functions execute a single SQL round-trip per call. The
matrix / trends / pareto endpoints feed straight into Pydantic response
models defined in `schemas.py`.

EXPLAIN notes (Postgres ≤ 10k task_results):
- `compute_matrix` issues one SELECT over `task_results` LEFT JOIN
  `submissions` LEFT JOIN `runs` (+ users/repos when an operator filter
  is active). The result set is grouped in Python by `(model, tier, suite)`.
  Index `ix_task_results_model_tier_suite` accelerates the filter step;
  trust + operator filters land on `submissions.trust_tier` and
  `users.handle`. Expected plan: Hash Left Join over task_results,
  no nested loops. p95 < 500 ms target for ≤ 10k rows; SQLite < 100 ms
  for the same payload.
- `compute_trends` is one GROUP BY over `task_results` filtered by
  (model, suite, tier, date >= cutoff). Date bucket is computed from
  `runs.started_at` (preferred) or `submissions.ingested_at`.
- `compute_pareto` is one GROUP BY (model, tier) over task_results.
  Frontier flag is computed in Python on the small result set
  (cardinality <= |models| × |tiers|).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import case, func
from sqlmodel import Session, select

from ab_server.models.repo import RegisteredRepo
from ab_server.models.run import Run
from ab_server.models.submission import Submission
from ab_server.models.task_result import TaskResult
from ab_server.models.user import User

from .schemas import (
    LeaderboardCell,
    LeaderboardMatrix,
    LeaderboardRow,
    ParetoPoint,
    ParetoSeries,
    TrendsPoint,
    TrendsSeries,
)


def _coalesce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    return None


def compute_matrix(
    session: Session,
    *,
    suites: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    tiers: Sequence[str] | None = None,
    operator: str | None = None,
    trust: Sequence[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
) -> LeaderboardMatrix:
    stmt = (
        select(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.suite,
            TaskResult.score_total,
            TaskResult.cost_usd,
            Run.started_at,
            Submission.ingested_at,
            Submission.trust_tier,
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
    )

    if operator is not None:
        stmt = stmt.join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        ).join(User, User.id == RegisteredRepo.user_id, isouter=True)
        stmt = stmt.where(User.handle == operator)

    if suites:
        stmt = stmt.where(TaskResult.suite.in_(list(suites)))
    if models:
        stmt = stmt.where(TaskResult.model.in_(list(models)))
    if tiers:
        stmt = stmt.where(TaskResult.tier.in_(list(tiers)))
    if trust:
        stmt = stmt.where(Submission.trust_tier.in_(list(trust)))
    effective_ts = case(
        (Run.started_at.is_not(None), Run.started_at),
        else_=Submission.ingested_at,
    )
    if date_from is not None:
        stmt = stmt.where(effective_ts >= date_from)
    if date_to is not None:
        stmt = stmt.where(effective_ts <= date_to)

    raw = session.exec(stmt).all()

    Bucket = tuple[str, str, str]
    scores: dict[Bucket, list[float]] = {}
    costs: dict[Bucket, list[float]] = {}
    latest: dict[Bucket, datetime | None] = {}
    trust_seen: dict[Bucket, list[str]] = {}
    suite_set: set[str] = set()

    for (
        model,
        tier,
        suite,
        score_total,
        cost_usd,
        started_at,
        ingested_at,
        trust_tier,
    ) in raw:
        key: Bucket = (model, tier, suite)
        suite_set.add(suite)
        scores.setdefault(key, []).append(float(score_total or 0.0))
        costs.setdefault(key, []).append(float(cost_usd or 0.0))
        candidate_ts = _coalesce_dt(started_at) or _coalesce_dt(ingested_at)
        if candidate_ts is not None:
            prev = latest.get(key)
            if prev is None or candidate_ts > prev:
                latest[key] = candidate_ts
        if trust_tier:
            bucket_trust = trust_seen.setdefault(key, [])
            if trust_tier not in bucket_trust:
                bucket_trust.append(trust_tier)

    cell_index: dict[tuple[str, str], dict[str, LeaderboardCell]] = {}
    row_sums: dict[tuple[str, str], list[float]] = {}

    for (model, tier, suite), score_list in scores.items():
        n = len(score_list)
        score_mean = sum(score_list) / n if n else 0.0
        cost_list = costs.get((model, tier, suite), [])
        cost_mean = sum(cost_list) / len(cost_list) if cost_list else 0.0
        cell = LeaderboardCell(
            score_mean=score_mean,
            n=n,
            latest_run_at=latest.get((model, tier, suite)),
            trust_tiers=trust_seen.get((model, tier, suite), []),
            cost_usd_mean=cost_mean,
        )
        cell_index.setdefault((model, tier), {})[suite] = cell
        row_sums.setdefault((model, tier), []).append(score_mean)

    suites_sorted = sorted(suite_set)
    rows: list[LeaderboardRow] = []
    for (model, tier), cells in sorted(cell_index.items()):
        row_scores = row_sums.get((model, tier), [])
        row_mean = sum(row_scores) / len(row_scores) if row_scores else 0.0
        rows.append(
            LeaderboardRow(
                model=model,
                tier=tier,
                cells=cells,
                row_mean=row_mean,
            )
        )

    filters_applied: dict[str, Any] = {}
    if suites:
        filters_applied["suites"] = list(suites)
    if models:
        filters_applied["models"] = list(models)
    if tiers:
        filters_applied["tiers"] = list(tiers)
    if operator:
        filters_applied["operator"] = operator
    if trust:
        filters_applied["trust"] = list(trust)
    if date_from:
        filters_applied["date_from"] = date_from.isoformat()
    if date_to:
        filters_applied["date_to"] = date_to.isoformat()

    return LeaderboardMatrix(
        rows=rows,
        suites=suites_sorted,
        generated_at=datetime.now(UTC),
        filters_applied=filters_applied,
    )


def compute_trends(
    session: Session,
    *,
    model: str,
    suite: str,
    tier: str,
    days: int,
) -> TrendsSeries:
    if days <= 0:
        return TrendsSeries(model=model, suite=suite, tier=tier, points=[])

    cutoff = datetime.now(UTC) - timedelta(days=days)

    date_proxy = case(
        (Run.started_at.is_not(None), Run.started_at),
        else_=Submission.ingested_at,
    )

    bucket = func.date(date_proxy).label("bucket")

    stmt = (
        select(
            bucket,
            func.avg(TaskResult.score_total).label("score_mean"),
            func.count(TaskResult.id).label("n"),
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .where(TaskResult.model == model)
        .where(TaskResult.suite == suite)
        .where(TaskResult.tier == tier)
        .where(date_proxy >= cutoff)
        .group_by(bucket)
        .order_by(bucket)
    )

    raw = session.exec(stmt).all()
    points: list[TrendsPoint] = []
    for bucket_val, score_mean, n in raw:
        if bucket_val is None:
            continue
        if isinstance(bucket_val, datetime):
            bucket_str = bucket_val.date().isoformat()
        elif isinstance(bucket_val, date):
            bucket_str = bucket_val.isoformat()
        else:
            bucket_str = str(bucket_val)
        points.append(
            TrendsPoint(
                date=bucket_str,
                score_mean=float(score_mean) if score_mean is not None else 0.0,
                n=int(n or 0),
            )
        )

    return TrendsSeries(model=model, suite=suite, tier=tier, points=points)


def compute_pareto(
    session: Session,
    *,
    suites: Sequence[str] | None = None,
    tiers: Sequence[str] | None = None,
) -> ParetoSeries:
    stmt = select(
        TaskResult.model,
        TaskResult.tier,
        func.avg(TaskResult.cost_usd).label("cost_mean"),
        func.avg(TaskResult.score_total).label("score_mean"),
        func.count(TaskResult.id).label("n"),
    ).group_by(TaskResult.model, TaskResult.tier)

    if suites:
        stmt = stmt.where(TaskResult.suite.in_(list(suites)))
    if tiers:
        stmt = stmt.where(TaskResult.tier.in_(list(tiers)))

    raw = session.exec(stmt).all()

    points: list[ParetoPoint] = []
    for model, tier, cost_mean, score_mean, n in raw:
        points.append(
            ParetoPoint(
                model=model,
                tier=tier,
                cost_usd_mean=float(cost_mean) if cost_mean is not None else 0.0,
                score_mean=float(score_mean) if score_mean is not None else 0.0,
                n=int(n or 0),
                on_frontier=False,
            )
        )

    for i, p in enumerate(points):
        dominated = False
        for j, q in enumerate(points):
            if i == j:
                continue
            if (
                q.cost_usd_mean <= p.cost_usd_mean
                and q.score_mean >= p.score_mean
                and (q.cost_usd_mean < p.cost_usd_mean or q.score_mean > p.score_mean)
            ):
                dominated = True
                break
        p.on_frontier = not dominated

    points.sort(key=lambda x: (x.cost_usd_mean, -x.score_mean))
    return ParetoSeries(points=points)
