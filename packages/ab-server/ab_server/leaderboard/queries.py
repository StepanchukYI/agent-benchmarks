"""Leaderboard aggregation queries.

All public functions execute a small, bounded number of SQL round-trips per
call (matrix = 2; trends/pareto/regressions/overview = 1). The matrix / trends
/ pareto endpoints feed straight into Pydantic response models defined in
`schemas.py`.

EXPLAIN notes (Postgres ≤ 10k task_results):
- `compute_matrix` issues one SELECT over `task_results` LEFT JOIN
  `submissions` LEFT JOIN `runs` (+ users/repos when an operator filter
  is active), plus a second SELECT for the 14-day sparkline / previous-window
  buckets. The first result set is grouped in Python by `(model, tier, suite)`.
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
- `compute_regressions` is one SELECT over the 2×window range; bucketing
  into the two windows happens in Python.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import case, func, or_
from sqlmodel import Session, select

from ab_server.models.alert import AlertRule
from ab_server.models.repo import RegisteredRepo
from ab_server.models.run import Run
from ab_server.models.submission import Submission
from ab_server.models.task_result import TaskResult
from ab_server.models.user import User

from .schemas import (
    CIGateStatus,
    DatasetPin,
    HeatmapCell,
    HeatmapResponse,
    HeatmapRow,
    LeaderboardCell,
    LeaderboardMatrix,
    LeaderboardMatrixRow,
    LeaderboardResponse,
    LeaderboardRow,
    LeaderboardSummary,
    ParetoHistoryPoint,
    ParetoHistorySeries,
    ParetoHistorySeriesItem,
    ParetoPoint,
    ParetoSeries,
    RegressionItem,
    RegressionsPanel,
    RowTaskItem,
    RowTaskScorerItem,
    TrendsOverview,
    TrendsPoint,
    TrendsSeries,
    TrendsSeriesResponse,
)

PILLARS: list[str] = [
    "Correctness",
    "Context",
    "Tool/Skill",
    "Memory",
    "Latency $",
]
# Maps the public API `pillar` query param (matches values of
# ab_harness.scorers.SCORER_PILLAR_MAP) to the index into LeaderboardRow.scores.
PILLAR_PARAM_TO_INDEX: dict[str, int] = {
    "correctness": 0,
    "context_efficiency": 1,
    "tool_skill": 2,
    "memory_specific": 3,
    "latency_cost": 4,
}
_TRUST_RANK = {"self_reported": 0, "verified": 1, "official": 2}


def _coalesce_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        return parsed
    return None


def _date_proxy():
    return case(
        (Run.started_at.is_not(None), Run.started_at),
        else_=Submission.ingested_at,
    )


def _dataset_version_proxy():
    return case(
        (Run.dataset_version.is_not(None), Run.dataset_version),
        else_=Submission.dataset_version,
    )


def _bucket_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _mean(values: Sequence[float]) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


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
    dataset_versions: Sequence[str] | None = None,
) -> LeaderboardMatrix:
    stmt = (
        select(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.suite,
            TaskResult.score_total,
            TaskResult.score_correctness,
            TaskResult.score_context_eff,
            TaskResult.score_tool_skill,
            TaskResult.score_memory,
            TaskResult.score_latency,
            TaskResult.cost_usd,
            Run.started_at,
            Submission.ingested_at,
            Submission.trust_tier,
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        # Always LEFT JOIN the repo so archived repos can be excluded.
        # delete_repo only soft-archives (status="archived") and leaves the
        # submissions in place; without this filter, unregister+re-register
        # of the same results repo double-counts every run (the bug that
        # turned 84 haiku runs into 168 on the board).
        .join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        )
    )
    # Drop submission rows whose repo is archived. Run-based rows (local
    # runs, no submission/repo) are kept via the NULL check.
    stmt = stmt.where(
        or_(
            Submission.registered_repo_id.is_(None),
            RegisteredRepo.status != "archived",
        )
    )

    if operator is not None:
        stmt = stmt.join(User, User.id == RegisteredRepo.user_id, isouter=True)
        stmt = stmt.where(User.handle == operator)

    if suites:
        stmt = stmt.where(TaskResult.suite.in_(list(suites)))
    if models:
        stmt = stmt.where(TaskResult.model.in_(list(models)))
    if tiers:
        stmt = stmt.where(TaskResult.tier.in_(list(tiers)))
    if trust:
        stmt = stmt.where(Submission.trust_tier.in_(list(trust)))
    if dataset_versions:
        stmt = stmt.where(_dataset_version_proxy().in_(list(dataset_versions)))
    effective_ts = _date_proxy()
    if date_from is not None:
        stmt = stmt.where(effective_ts >= date_from)
    if date_to is not None:
        stmt = stmt.where(effective_ts <= date_to)

    raw = session.exec(stmt).all()

    Bucket = tuple[str, str, str]
    scores: dict[Bucket, list[float]] = {}
    correctness: dict[Bucket, list[float]] = {}
    context_eff: dict[Bucket, list[float]] = {}
    tool_skill: dict[Bucket, list[float]] = {}
    memory_p: dict[Bucket, list[float]] = {}
    latency_p: dict[Bucket, list[float]] = {}
    costs: dict[Bucket, list[float]] = {}
    latest: dict[Bucket, datetime | None] = {}
    trust_seen: dict[Bucket, list[str]] = {}
    suite_set: set[str] = set()

    for (
        model,
        tier,
        suite,
        score_total,
        s_correct,
        s_context,
        s_tool,
        s_mem,
        s_lat,
        cost_usd,
        started_at,
        ingested_at,
        trust_tier,
    ) in raw:
        key: Bucket = (model, tier, suite)
        suite_set.add(suite)
        scores.setdefault(key, []).append(float(score_total or 0.0))
        if s_correct is not None:
            correctness.setdefault(key, []).append(float(s_correct))
        if s_context is not None:
            context_eff.setdefault(key, []).append(float(s_context))
        if s_tool is not None:
            tool_skill.setdefault(key, []).append(float(s_tool))
        if s_mem is not None:
            memory_p.setdefault(key, []).append(float(s_mem))
        if s_lat is not None:
            latency_p.setdefault(key, []).append(float(s_lat))
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

    sparkline_window = 7
    cutoff_now = datetime.now(UTC) - timedelta(days=2 * sparkline_window)

    spark_stmt = (
        select(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.suite,
            func.date(_date_proxy()).label("bucket"),
            func.avg(TaskResult.score_total).label("score_mean"),
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .where(_date_proxy() >= cutoff_now)
        .group_by(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.suite,
            func.date(_date_proxy()),
        )
    )
    if suites:
        spark_stmt = spark_stmt.where(TaskResult.suite.in_(list(suites)))
    if models:
        spark_stmt = spark_stmt.where(TaskResult.model.in_(list(models)))
    if tiers:
        spark_stmt = spark_stmt.where(TaskResult.tier.in_(list(tiers)))
    if trust:
        spark_stmt = spark_stmt.where(Submission.trust_tier.in_(list(trust)))
    if dataset_versions:
        spark_stmt = spark_stmt.where(
            _dataset_version_proxy().in_(list(dataset_versions))
        )
    if operator is not None:
        spark_stmt = spark_stmt.join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        ).join(User, User.id == RegisteredRepo.user_id, isouter=True)
        spark_stmt = spark_stmt.where(User.handle == operator)

    today = datetime.now(UTC).date()
    current_floor = today - timedelta(days=sparkline_window - 1)
    prev_floor = today - timedelta(days=2 * sparkline_window - 1)
    prev_ceil = today - timedelta(days=sparkline_window)

    current_by_day: dict[Bucket, dict[str, float]] = {}
    prev_scores: dict[Bucket, list[float]] = {}

    for model, tier, suite, bucket_val, score_mean in session.exec(spark_stmt).all():
        if bucket_val is None or score_mean is None:
            continue
        if isinstance(bucket_val, datetime):
            day = bucket_val.date()
        elif isinstance(bucket_val, date):
            day = bucket_val
        else:
            try:
                day = datetime.fromisoformat(str(bucket_val)).date()
            except ValueError:
                continue
        key = (model, tier, suite)
        day_iso = day.isoformat()
        if day >= current_floor:
            current_by_day.setdefault(key, {})[day_iso] = float(score_mean)
        elif prev_floor <= day <= prev_ceil:
            prev_scores.setdefault(key, []).append(float(score_mean))

    cell_index: dict[tuple[str, str], dict[str, LeaderboardCell]] = {}
    row_sums: dict[tuple[str, str], list[float]] = {}

    for (model, tier, suite), score_list in scores.items():
        n = len(score_list)
        score_mean = sum(score_list) / n if n else 0.0
        cost_list = costs.get((model, tier, suite), [])
        cost_mean = sum(cost_list) / len(cost_list) if cost_list else 0.0

        spark_days = current_by_day.get((model, tier, suite), {})
        sparkline_7d: list[float] = []
        for offset in range(sparkline_window - 1, -1, -1):
            day = today - timedelta(days=offset)
            if day.isoformat() in spark_days:
                sparkline_7d.append(spark_days[day.isoformat()])

        prev_list = prev_scores.get((model, tier, suite), [])
        previous_mean = sum(prev_list) / len(prev_list) if prev_list else None
        delta = score_mean - previous_mean if previous_mean is not None else None

        cell = LeaderboardCell(
            score_mean=score_mean,
            n=n,
            latest_run_at=latest.get((model, tier, suite)),
            trust_tiers=trust_seen.get((model, tier, suite), []),
            cost_usd_mean=cost_mean,
            score_correctness=_mean(correctness.get((model, tier, suite), [])),
            score_context_eff=_mean(context_eff.get((model, tier, suite), [])),
            score_tool_skill=_mean(tool_skill.get((model, tier, suite), [])),
            score_memory=_mean(memory_p.get((model, tier, suite), [])),
            score_latency=_mean(latency_p.get((model, tier, suite), [])),
            sparkline_7d=sparkline_7d,
            previous_mean=previous_mean,
            delta=delta,
        )
        cell_index.setdefault((model, tier), {})[suite] = cell
        row_sums.setdefault((model, tier), []).append(score_mean)

    suites_sorted = sorted(suite_set)
    rows: list[LeaderboardMatrixRow] = []
    for (model, tier), cells in sorted(cell_index.items()):
        row_scores = row_sums.get((model, tier), [])
        row_mean = sum(row_scores) / len(row_scores) if row_scores else 0.0
        rows.append(
            LeaderboardMatrixRow(
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
    if dataset_versions:
        filters_applied["dataset_versions"] = list(dataset_versions)

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

    date_proxy = _date_proxy()

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
        bucket_str = _bucket_date(bucket_val)
        if bucket_str is None:
            continue
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


def compute_heatmap(
    session: Session,
    *,
    suites: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    tiers: Sequence[str] | None = None,
) -> HeatmapResponse:
    """Per (model, tier) × suite mean correctness, for the FE ScoreHeatmap.

    One GROUP BY over task_results. Each cell is the mean of
    ``score_correctness`` (0..1) over the rows in that (model, tier, suite)
    bucket, plus the row count. Empty DB returns rows=[], suites=[].
    """
    stmt = (
        select(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.suite,
            func.avg(TaskResult.score_correctness).label("corr_mean"),
            func.count(TaskResult.id).label("n"),
        )
        .group_by(TaskResult.model, TaskResult.tier, TaskResult.suite)
    )
    if suites:
        stmt = stmt.where(TaskResult.suite.in_(list(suites)))
    if models:
        stmt = stmt.where(TaskResult.model.in_(list(models)))
    if tiers:
        stmt = stmt.where(TaskResult.tier.in_(list(tiers)))

    raw = session.exec(stmt).all()

    cell_index: dict[tuple[str, str], dict[str, HeatmapCell]] = {}
    suite_set: set[str] = set()
    for model, tier, suite, corr_mean, n in raw:
        suite_set.add(suite)
        cell_index.setdefault((model, tier), {})[suite] = HeatmapCell(
            score_correctness=float(corr_mean) if corr_mean is not None else None,
            n=int(n or 0),
        )

    rows = [
        HeatmapRow(model=model, tier=tier, cells=cells)
        for (model, tier), cells in sorted(cell_index.items())
    ]
    return HeatmapResponse(
        rows=rows,
        suites=sorted(suite_set),
        generated_at=datetime.now(UTC),
    )


def _iso_week_floor(value: datetime) -> datetime:
    """Monday 00:00 UTC of the ISO week containing ``value``."""
    d = value.astimezone(UTC)
    monday = d.date() - timedelta(days=d.weekday())
    return datetime(monday.year, monday.month, monday.day, tzinfo=UTC)


def compute_pareto_history(
    session: Session,
    *,
    window_days: int = 30,
    suites: Sequence[str] | None = None,
    tiers: Sequence[str] | None = None,
) -> ParetoHistorySeries:
    """Historical (cost, correctness-via-score_total) trail per (model, tier).

    One SELECT over task_results within [now - window_days, now), bucketed
    by ISO week in Python (so the date proxy is reused). Each point is the
    mean cost_usd and mean score_total for that (model, tier) in that week.
    Empty DB / empty window returns series=[].
    """
    if window_days <= 0:
        return ParetoHistorySeries(series=[], window_days=0, generated_at=datetime.now(UTC))

    cutoff = datetime.now(UTC) - timedelta(days=window_days)
    date_proxy = _date_proxy()

    stmt = (
        select(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.cost_usd,
            TaskResult.score_total,
            date_proxy.label("ts"),
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .where(date_proxy >= cutoff)
    )
    if suites:
        stmt = stmt.where(TaskResult.suite.in_(list(suites)))
    if tiers:
        stmt = stmt.where(TaskResult.tier.in_(list(tiers)))

    Bucket = tuple[str, str, datetime]
    costs: dict[Bucket, list[float]] = {}
    scores: dict[Bucket, list[float]] = {}
    for model, tier, cost_usd, score_total, ts_val in session.exec(stmt).all():
        ts = _coalesce_dt(ts_val)
        if ts is None:
            continue
        week = _iso_week_floor(ts)
        key: Bucket = (model, tier, week)
        costs.setdefault(key, []).append(float(cost_usd or 0.0))
        scores.setdefault(key, []).append(float(score_total or 0.0))

    by_series: dict[tuple[str, str], list[ParetoHistoryPoint]] = {}
    for (model, tier, week), cost_list in costs.items():
        score_list = scores.get((model, tier, week), [])
        by_series.setdefault((model, tier), []).append(
            ParetoHistoryPoint(
                at=week,
                cost_usd_mean=sum(cost_list) / len(cost_list) if cost_list else 0.0,
                score_mean=sum(score_list) / len(score_list) if score_list else 0.0,
                n=len(cost_list),
            )
        )

    series: list[ParetoHistorySeriesItem] = []
    for (model, tier), points in sorted(by_series.items()):
        points.sort(key=lambda p: p.at)
        series.append(
            ParetoHistorySeriesItem(model=model, tier=tier, history=points)
        )

    return ParetoHistorySeries(
        series=series,
        window_days=window_days,
        generated_at=datetime.now(UTC),
    )


def _collect_regression_buckets(
    session: Session,
    *,
    window_days: int,
    now: datetime,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    floor = now - timedelta(days=2 * window_days)
    current_floor = now - timedelta(days=window_days)

    stmt = (
        select(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.suite,
            TaskResult.score_total,
            _date_proxy().label("ts"),
            User.handle,
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        )
        .join(User, User.id == RegisteredRepo.user_id, isouter=True)
        .where(_date_proxy() >= floor)
    )

    buckets: dict[tuple[str, str, str], dict[str, Any]] = {}
    for model, tier, suite, score_total, ts_val, handle in session.exec(stmt).all():
        ts = _coalesce_dt(ts_val)
        if ts is None:
            continue
        key = (model, tier, suite)
        entry = buckets.setdefault(
            key,
            {
                "current": [],
                "prev": [],
                "last_run_at": None,
                "operator": None,
            },
        )
        score_val = float(score_total or 0.0)
        if ts >= current_floor:
            entry["current"].append(score_val)
            if entry["last_run_at"] is None or ts > entry["last_run_at"]:
                entry["last_run_at"] = ts
                if handle:
                    entry["operator"] = handle
        else:
            entry["prev"].append(score_val)
    return buckets


def compute_regressions(
    session: Session,
    *,
    window_days: int = 7,
    min_delta: float = 0.05,
    direction: str = "down",
    limit: int = 5,
) -> RegressionsPanel:
    if direction not in ("up", "down"):
        raise ValueError(f"direction must be 'up' or 'down', got {direction!r}")
    if window_days <= 0:
        return RegressionsPanel(direction=direction, window_days=window_days, items=[])

    now = datetime.now(UTC)
    buckets = _collect_regression_buckets(session, window_days=window_days, now=now)

    items: list[RegressionItem] = []
    for (model, tier, suite), entry in buckets.items():
        cur = entry["current"]
        prev = entry["prev"]
        if not cur or not prev:
            continue
        score_now = sum(cur) / len(cur)
        score_prev = sum(prev) / len(prev)
        delta = score_now - score_prev
        if direction == "down" and delta > -min_delta:
            continue
        if direction == "up" and delta < min_delta:
            continue
        items.append(
            RegressionItem(
                model=model,
                tier=tier,
                suite=suite,
                score_now=score_now,
                score_prev=score_prev,
                delta_pct=delta,
                n_now=len(cur),
                n_prev=len(prev),
                last_run_at=entry["last_run_at"],
                operator_handle=entry["operator"],
            )
        )

    reverse = direction == "up"
    items.sort(key=lambda i: i.delta_pct, reverse=reverse)
    return RegressionsPanel(
        direction=direction,
        window_days=window_days,
        items=items[:limit],
    )


def _last_full_sweep_at(session: Session) -> datetime | None:
    stmt = select(func.max(Run.finished_at)).where(Run.status == "completed")
    value = session.exec(stmt).one()
    if isinstance(value, tuple):
        value = value[0]
    return _coalesce_dt(value)


def _alerts_fired_in_window(session: Session, *, window_days: int, now: datetime) -> int:
    """Count alert rules that fired within the last ``window_days``.

    Mirrors AlertRule.derive_state's "firing" definition (fired no more than
    window_days ago). Platform-wide count — not user-scoped — consistent with
    the rest of the overview.
    """
    floor = now - timedelta(days=window_days)
    stmt = select(func.count(AlertRule.id)).where(
        AlertRule.last_fired_at.is_not(None),
        AlertRule.last_fired_at >= floor,
    )
    value = session.exec(stmt).one()
    if isinstance(value, tuple):
        value = value[0]
    return int(value or 0)


def _collect_regression_buckets_window(
    session: Session,
    *,
    current_from: datetime,
    current_to: datetime,
    prev_from: datetime,
    prev_to: datetime,
) -> dict[tuple[str, str, str], dict[str, list[float]]]:
    """Bucket scores into current/prev windows using explicit bounds.

    Unlike `_collect_regression_buckets`, this version applies upper bounds
    so anchored windows can sit anywhere on the timeline (the rolling
    helper only filters by a single floor and leaks more-recent data in).
    """
    stmt = (
        select(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.suite,
            TaskResult.score_total,
            _date_proxy().label("ts"),
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .where(_date_proxy() >= prev_from)
        .where(_date_proxy() < current_to)
    )
    buckets: dict[tuple[str, str, str], dict[str, list[float]]] = {}
    for model, tier, suite, score_total, ts_val in session.exec(stmt).all():
        ts = _coalesce_dt(ts_val)
        if ts is None:
            continue
        key = (model, tier, suite)
        entry = buckets.setdefault(key, {"current": [], "prev": []})
        score_val = float(score_total or 0.0)
        if current_from <= ts < current_to:
            entry["current"].append(score_val)
        elif prev_from <= ts < prev_to:
            entry["prev"].append(score_val)
    return buckets


def _count_regressions_window(
    buckets: dict[tuple[str, str, str], dict[str, list[float]]],
    *,
    direction: str,
    min_delta: float = 0.05,
) -> int:
    count = 0
    for entry in buckets.values():
        cur = entry["current"]
        prev = entry["prev"]
        if not cur or not prev:
            continue
        delta = (sum(cur) / len(cur)) - (sum(prev) / len(prev))
        if (direction == "down" and delta <= -min_delta) or (direction == "up" and delta >= min_delta):
            count += 1
    return count


def compute_overview(
    session: Session,
    *,
    window_days: int = 7,
) -> TrendsOverview:
    down = compute_regressions(
        session,
        window_days=window_days,
        min_delta=0.05,
        direction="down",
        limit=1000,
    )
    up = compute_regressions(
        session,
        window_days=window_days,
        min_delta=0.05,
        direction="up",
        limit=1000,
    )

    ci_buckets = _collect_regression_buckets(
        session,
        window_days=2,
        now=datetime.now(UTC),
    )
    blocked = 0
    for entry in ci_buckets.values():
        cur = entry["current"]
        prev = entry["prev"]
        if not cur or not prev:
            continue
        delta = (sum(cur) / len(cur)) - (sum(prev) / len(prev))
        if delta < -0.05:
            blocked += 1
    status = "failing" if blocked > 0 else "passing"

    # 30d delta vs prior 30d window. Two explicit window pairs:
    #   current comparison: [now-30d, now)        vs [now-60d, now-30d)
    #   prior comparison:   [now-60d, now-30d)    vs [now-90d, now-60d)
    # Delta = current_count - prior_count. Null when the prior 30d window
    # [now-60d, now-30d) is empty.
    now_ts = datetime.now(UTC)
    cur_from_30 = now_ts - timedelta(days=30)
    prev_from_30 = now_ts - timedelta(days=60)
    cur_buckets_30 = _collect_regression_buckets_window(
        session,
        current_from=cur_from_30,
        current_to=now_ts,
        prev_from=prev_from_30,
        prev_to=cur_from_30,
    )
    prior_from_30 = now_ts - timedelta(days=60)
    prior_prev_from_30 = now_ts - timedelta(days=90)
    prior_buckets_30 = _collect_regression_buckets_window(
        session,
        current_from=prior_from_30,
        current_to=cur_from_30,
        prev_from=prior_prev_from_30,
        prev_to=prior_from_30,
    )
    has_prior = any(entry["current"] for entry in prior_buckets_30.values())
    if has_prior:
        cur_down_30 = _count_regressions_window(cur_buckets_30, direction="down")
        cur_up_30 = _count_regressions_window(cur_buckets_30, direction="up")
        prior_down = _count_regressions_window(prior_buckets_30, direction="down")
        prior_up = _count_regressions_window(prior_buckets_30, direction="up")
        active_regressions_delta_30d: int | None = cur_down_30 - prior_down
        improvements_delta_30d: int | None = cur_up_30 - prior_up
    else:
        active_regressions_delta_30d = None
        improvements_delta_30d = None

    return TrendsOverview(
        window_days=window_days,
        active_regressions_count=len(down.items),
        improvements_count=len(up.items),
        active_regressions_delta_30d=active_regressions_delta_30d,
        improvements_delta_30d=improvements_delta_30d,
        ci_gate_status=status,
        ci_gate_blocked_merges_48h=blocked,
        alerts_count_window=_alerts_fired_in_window(
            session, window_days=window_days, now=now_ts
        ),
        # No acknowledged/resolved field on AlertRule, and no scheduled
        # full-sweep mechanism exists — surface honest None rather than a
        # fabricated 0 / cadence string.
        alerts_actioned=None,
        last_full_sweep_at=_last_full_sweep_at(session),
        last_full_sweep_cadence=None,
    )


def compute_ci_gate(session: Session) -> CIGateStatus:
    overview = compute_overview(session, window_days=7)
    return CIGateStatus(
        status=overview.ci_gate_status,
        blocked_merges_48h=overview.ci_gate_blocked_merges_48h,
        threshold_pct=0.05,
        computed_at=datetime.now(UTC),
    )


def _median(values: Sequence[float]) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return float(s[mid])
    return float((s[mid - 1] + s[mid]) / 2.0)


def _stddev(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    m = sum(values) / len(values)
    var = sum((x - m) ** 2 for x in values) / (len(values) - 1)
    return float(var ** 0.5)


def _best_trust(trusts: Sequence[str]) -> str:
    if not trusts:
        return "self_reported"
    return max(trusts, key=lambda t: _TRUST_RANK.get(t, -1))


def _summary_aggregate(
    session: Session,
    *,
    suites: Sequence[str] | None,
    models: Sequence[str] | None,
    tiers: Sequence[str] | None,
    operators: Sequence[str] | None,
    trust: Sequence[str] | None,
    dataset_versions: Sequence[str] | None,
    date_from: datetime,
    date_to: datetime,
) -> dict[str, Any]:
    """One SQL aggregation over a [date_from, date_to) window.

    Returns aggregate dict with keys:
      - mean_correctness: float | None (0..1 mean across rows in window)
      - runs_count: int (distinct (run_id, submission_id) buckets)
      - per_model: dict[str, tuple[float, float]]  -> (mean_corr, mean_cost)
      - mean_pass_rate: float | None  (100 * passed_true / decided, or None)
    """
    stmt = (
        select(
            TaskResult.model,
            TaskResult.score_correctness,
            TaskResult.cost_usd,
            TaskResult.run_id,
            TaskResult.submission_id,
            TaskResult.passed,
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        )
        .join(User, User.id == RegisteredRepo.user_id, isouter=True)
        .where(_date_proxy() >= date_from)
        .where(_date_proxy() < date_to)
    )
    if suites:
        stmt = stmt.where(TaskResult.suite.in_(list(suites)))
    if models:
        stmt = stmt.where(TaskResult.model.in_(list(models)))
    if tiers:
        stmt = stmt.where(TaskResult.tier.in_(list(tiers)))
    if trust:
        stmt = stmt.where(Submission.trust_tier.in_(list(trust)))
    if dataset_versions:
        stmt = stmt.where(_dataset_version_proxy().in_(list(dataset_versions)))
    if operators:
        stmt = stmt.where(User.handle.in_(list(operators)))

    raw = session.exec(stmt).all()

    corr_vals: list[float] = []
    per_model_corr: dict[str, list[float]] = {}
    per_model_cost: dict[str, list[float]] = {}
    run_keys: set[tuple[Any, Any]] = set()
    pass_true = 0
    pass_decided = 0

    for model, s_corr, cost_usd, run_id, sub_id, passed in raw:
        # Skip rows where correctness was not measured (None) so the KPI mean
        # isn't dragged down by a phantom 0; a genuine measured 0.0 still counts.
        if s_corr is not None:
            c = float(s_corr)
            corr_vals.append(c)
            per_model_corr.setdefault(model, []).append(c)
        per_model_cost.setdefault(model, []).append(float(cost_usd or 0.0))
        # Count distinct run "groups": either run_id (local) or submission_id (pulled).
        if run_id is not None or sub_id is not None:
            run_keys.add((run_id, sub_id))
        # Accumulate pass stats. None = no decided scorer → skip.
        if passed is not None:
            pass_decided += 1
            if passed:
                pass_true += 1

    per_model: dict[str, tuple[float, float]] = {}
    for m, cs in per_model_corr.items():
        mean_c = sum(cs) / len(cs)
        cost_list = per_model_cost.get(m, [])
        mean_cost = sum(cost_list) / len(cost_list) if cost_list else 0.0
        per_model[m] = (mean_c, mean_cost)

    mean_pass_rate: float | None = (
        100.0 * pass_true / pass_decided if pass_decided > 0 else None
    )
    return {
        "mean_correctness": (sum(corr_vals) / len(corr_vals)) if corr_vals else None,
        "n_rows": len(corr_vals),
        "runs_count": len(run_keys),
        "per_model": per_model,
        "mean_pass_rate": mean_pass_rate,
    }


def compute_leaderboard_summary(
    session: Session,
    *,
    suites: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    tiers: Sequence[str] | None = None,
    operators: Sequence[str] | None = None,
    trust: Sequence[str] | None = None,
    dataset_versions: Sequence[str] | None = None,
    range_days: int = 7,
    now: datetime | None = None,
) -> LeaderboardSummary | None:
    """Compute KPI summary over the current window and deltas vs prev window.

    Two SQL aggregations: one for [now - range, now), one for
    [now - 2*range, now - range). All deltas are null if the prev window
    has zero rows. Returns None when the current window is empty.
    """
    if range_days <= 0:
        range_days = 7
    now_ts = now if now is not None else datetime.now(UTC)
    cur_from = now_ts - timedelta(days=range_days)
    cur_to = now_ts
    prev_from = now_ts - timedelta(days=2 * range_days)
    prev_to = cur_from

    cur = _summary_aggregate(
        session,
        suites=suites,
        models=models,
        tiers=tiers,
        operators=operators,
        trust=trust,
        dataset_versions=dataset_versions,
        date_from=cur_from,
        date_to=cur_to,
    )
    if cur["n_rows"] == 0:
        return None

    prev = _summary_aggregate(
        session,
        suites=suites,
        models=models,
        tiers=tiers,
        operators=operators,
        trust=trust,
        dataset_versions=dataset_versions,
        date_from=prev_from,
        date_to=prev_to,
    )
    has_prev = prev["n_rows"] > 0

    cur_per_model: dict[str, tuple[float, float]] = cur["per_model"]
    # Best correctness: max mean correctness across models in current window.
    best_corr_model = max(
        cur_per_model.items(), key=lambda kv: kv[1][0]
    )[0] if cur_per_model else None
    best_corr_value = (
        cur_per_model[best_corr_model][0] if best_corr_model is not None else None
    )

    # Best cost efficiency: smallest (mean_cost / mean_correctness) across models
    # in the current window. Skip models with mean_correctness <= 0 (avoid div0).
    def _eff(pair: tuple[float, float]) -> float | None:
        mean_c, mean_cost = pair
        if mean_c <= 0:
            return None
        return mean_cost / mean_c

    eff_candidates = [
        (m, _eff(pair)) for m, pair in cur_per_model.items()
    ]
    eff_candidates = [(m, v) for m, v in eff_candidates if v is not None]
    if eff_candidates:
        best_eff_model, best_eff_value = min(eff_candidates, key=lambda kv: kv[1])
    else:
        best_eff_model, best_eff_value = None, None

    # Deltas vs prev window. Null when prev window is empty.
    if has_prev:
        prev_per_model: dict[str, tuple[float, float]] = prev["per_model"]
        mean_corr_delta: float | None = (
            cur["mean_correctness"] - prev["mean_correctness"]
        )
        runs_count_delta: int | None = cur["runs_count"] - prev["runs_count"]
        if best_corr_model is not None and best_corr_model in prev_per_model:
            best_corr_delta: float | None = (
                best_corr_value - prev_per_model[best_corr_model][0]
            )
        else:
            best_corr_delta = None
        if best_eff_model is not None and best_eff_model in prev_per_model:
            prev_eff = _eff(prev_per_model[best_eff_model])
            best_eff_delta: float | None = (
                (best_eff_value - prev_eff) if prev_eff is not None else None
            )
        else:
            best_eff_delta = None
    else:
        mean_corr_delta = None
        runs_count_delta = None
        best_corr_delta = None
        best_eff_delta = None

    return LeaderboardSummary(
        mean_correctness=cur["mean_correctness"],
        mean_correctness_delta=mean_corr_delta,
        runs_count_window=cur["runs_count"],
        runs_count_delta=runs_count_delta,
        best_correctness_model=best_corr_model,
        best_correctness_value=best_corr_value,
        best_correctness_delta=best_corr_delta,
        best_cost_efficiency_model=best_eff_model,
        best_cost_efficiency_value_usd=best_eff_value,
        best_cost_efficiency_delta=best_eff_delta,
        mean_pass_rate=cur["mean_pass_rate"],
    )


def compute_leaderboard_response(
    session: Session,
    *,
    suites: Sequence[str] | None = None,
    models: Sequence[str] | None = None,
    tiers: Sequence[str] | None = None,
    operators: Sequence[str] | None = None,
    trust: Sequence[str] | None = None,
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    dataset_versions: Sequence[str] | None = None,
    range_days: int | None = None,
    include_task_tags: Sequence[str] | None = None,
    exclude_task_tags: Sequence[str] | None = None,
    pillar: str | None = None,
) -> LeaderboardResponse:
    if range_days is not None and range_days > 0 and date_from is None:
        date_from = datetime.now(UTC) - timedelta(days=range_days)

    stmt = (
        select(
            TaskResult.model,
            TaskResult.tier,
            TaskResult.suite,
            TaskResult.task_id,
            TaskResult.score_total,
            TaskResult.score_correctness,
            TaskResult.score_context_eff,
            TaskResult.score_tool_skill,
            TaskResult.score_memory,
            TaskResult.score_latency,
            TaskResult.cost_usd,
            TaskResult.latency_ms,
            TaskResult.tokens_total,
            TaskResult.turns_total,
            TaskResult.passed,
            Submission.trust_tier,
            Submission.source_commit_sha,
            Submission.dataset_version,
            Submission.ingested_at,
            Run.dataset_version,
            Run.started_at,
            User.handle,
            TaskResult.harness,
            TaskResult.effort,
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        )
        .join(User, User.id == RegisteredRepo.user_id, isouter=True)
    )

    if suites:
        stmt = stmt.where(TaskResult.suite.in_(list(suites)))
    if models:
        stmt = stmt.where(TaskResult.model.in_(list(models)))
    if tiers:
        stmt = stmt.where(TaskResult.tier.in_(list(tiers)))
    if trust:
        stmt = stmt.where(Submission.trust_tier.in_(list(trust)))
    if dataset_versions:
        stmt = stmt.where(_dataset_version_proxy().in_(list(dataset_versions)))
    if operators:
        stmt = stmt.where(User.handle.in_(list(operators)))
    effective_ts = _date_proxy()
    if date_from is not None:
        stmt = stmt.where(effective_ts >= date_from)
    if date_to is not None:
        stmt = stmt.where(effective_ts <= date_to)

    raw = session.exec(stmt).all()

    # Sensitivity-tag filtering — Track B's per-task tags
    # (docs/result-sensitivity-axes.md). We filter post-SQL because
    # tags live on disk YAMLs, not the DB. The set is small (39 L0
    # task ids in v1; <1ms lookup per row).
    if include_task_tags or exclude_task_tags:
        from ab_server.leaderboard.task_tags import task_matches_filters

        inc = frozenset(include_task_tags) if include_task_tags else None
        exc = frozenset(exclude_task_tags) if exclude_task_tags else None
        raw = [row for row in raw if task_matches_filters(row[3], include=inc, exclude=exc)]

    # Bucket = (model, operator, tier, harness, effort): each distinct config
    # is its own leaderboard row. tier/harness/effort are part of the key so
    # aggregates never conflate runs with different configs.
    Bucket = tuple[str, str, str, str | None, str | None]
    pillar_keys = ("correctness", "context_eff", "tool_skill", "memory", "latency")
    scores: dict[Bucket, list[float]] = {}
    pillars_by_key: dict[Bucket, dict[str, list[float]]] = {}
    costs: dict[Bucket, list[float]] = {}
    latencies_ms: dict[Bucket, list[float]] = {}
    tokens_by_key: dict[Bucket, list[int]] = {}
    turns_by_key: dict[Bucket, list[int]] = {}
    suites_seen: dict[Bucket, list[str]] = {}
    tasks_seen: dict[Bucket, set[tuple[str, str]]] = {}
    sweep_cost: dict[Bucket, float] = {}
    trust_by_key: dict[Bucket, list[str]] = {}
    shas: dict[Bucket, tuple[str, datetime]] = {}
    versions_by_key: dict[Bucket, list[tuple[str, datetime | None]]] = {}
    # pass counts: [passed_true_count, decided_count]
    # decided = rows where passed is not None; pass_rate = true/decided
    pass_counts: dict[Bucket, list[int]] = {}

    for row in raw:
        (
            model,
            tier,
            suite,
            task_id,
            score_total,
            s_corr,
            s_ctx,
            s_tool,
            s_mem,
            s_lat,
            cost_usd,
            latency_ms,
            tokens_total,
            turns_total,
            passed,
            trust_tier,
            commit_sha,
            sub_dataset_version,
            ingested_at,
            run_dataset_version,
            started_at,
            handle,
            harness,
            effort,
        ) = row

        operator = handle or "self"
        key: Bucket = (model, operator, tier, harness, effort)
        scores.setdefault(key, []).append(float(score_total or 0.0))
        bucket_pillars = pillars_by_key.setdefault(
            key, {k: [] for k in pillar_keys}
        )
        # A pillar column is None when the task did not measure that pillar, and
        # a float (including a genuine 0.0) when it did. Count only non-None
        # contributions — a real 0.0 IS data. A pillar with zero non-None
        # contributions aggregates to an empty list → null downstream.
        for pillar_key, raw_score in (
            ("correctness", s_corr),
            ("context_eff", s_ctx),
            ("tool_skill", s_tool),
            ("memory", s_mem),
            ("latency", s_lat),
        ):
            if raw_score is not None:
                bucket_pillars[pillar_key].append(float(raw_score))
        costs.setdefault(key, []).append(float(cost_usd or 0.0))
        latencies_ms.setdefault(key, []).append(float(latency_ms or 0))
        tokens_by_key.setdefault(key, []).append(int(tokens_total or 0))
        turns_by_key.setdefault(key, []).append(int(turns_total or 0))
        suites_seen.setdefault(key, []).append(suite)
        tasks_seen.setdefault(key, set()).add((task_id, suite))
        if suite.startswith("L0_") or suite.startswith("L1_"):
            sweep_cost[key] = sweep_cost.get(key, 0.0) + float(cost_usd or 0.0)
        if trust_tier:
            trust_by_key.setdefault(key, []).append(trust_tier)
        ts = _coalesce_dt(started_at) or _coalesce_dt(ingested_at)
        if commit_sha:
            ts_for_sha = ts or datetime.min.replace(tzinfo=UTC)
            existing = shas.get(key)
            if existing is None or ts_for_sha > existing[1]:
                shas[key] = (commit_sha, ts_for_sha)
        ver = run_dataset_version or sub_dataset_version
        if ver:
            versions_by_key.setdefault(key, []).append((ver, ts))
        # Accumulate pass counts: [true_count, decided_count]
        # passed=None rows are skipped (no decided scorer → not measured).
        if passed is not None:
            pc = pass_counts.setdefault(key, [0, 0])
            pc[1] += 1
            if passed:
                pc[0] += 1

    prev_window = 7 if range_days is None or range_days <= 0 else range_days
    now_ts = datetime.now(UTC)
    prev_cutoff = now_ts - timedelta(days=2 * prev_window)
    prev_floor = now_ts - timedelta(days=prev_window)

    prev_stmt = (
        select(
            TaskResult.model,
            TaskResult.score_correctness,
            TaskResult.score_context_eff,
            TaskResult.score_tool_skill,
            TaskResult.score_memory,
            TaskResult.score_latency,
            User.handle,
            TaskResult.tier,
            TaskResult.harness,
            TaskResult.effort,
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        )
        .join(User, User.id == RegisteredRepo.user_id, isouter=True)
        .where(_date_proxy() >= prev_cutoff)
        .where(_date_proxy() < prev_floor)
    )
    if models:
        prev_stmt = prev_stmt.where(TaskResult.model.in_(list(models)))
    if operators:
        prev_stmt = prev_stmt.where(User.handle.in_(list(operators)))
    prev_pillars: dict[Bucket, dict[str, list[float]]] = {}
    for prow in session.exec(prev_stmt).all():
        model_p, c_p, ctx_p, tool_p, mem_p, lat_p, handle_p, tier_p, harness_p, effort_p = prow
        kp: Bucket = (model_p, handle_p or "self", tier_p, harness_p, effort_p)
        bp = prev_pillars.setdefault(kp, {k: [] for k in pillar_keys})
        # Same non-None rule as the current window so prev-window pillar means
        # (used for deltas) count genuine 0.0s and ignore unmeasured pillars.
        for pillar_key, raw_score in (
            ("correctness", c_p),
            ("context_eff", ctx_p),
            ("tool_skill", tool_p),
            ("memory", mem_p),
            ("latency", lat_p),
        ):
            if raw_score is not None:
                bp[pillar_key].append(float(raw_score))

    out_rows: list[LeaderboardRow] = []
    for key, score_list in scores.items():
        model, operator, row_tier, row_harness, row_effort = key
        bucket_pillars = pillars_by_key.get(key, {k: [] for k in pillar_keys})
        # Null (not 0) when a pillar had no measured contribution, so the FE can
        # skip it in the overall mean instead of averaging in a phantom zero.
        scores_arr: list[float | None] = [
            (sum(bucket_pillars[k]) / len(bucket_pillars[k]) * 100.0)
            if bucket_pillars[k]
            else None
            for k in pillar_keys
        ]
        # Sample size per pillar: number of task-results with a non-null score,
        # index-aligned to scores_arr (and to PILLARS / pillar_keys order).
        counts_arr: list[int] = [len(bucket_pillars[k]) for k in pillar_keys]
        prev_bp = prev_pillars.get(key)
        if prev_bp is None:
            delta_arr: list[float | None] = [None] * 5
        else:
            prev_arr: list[float | None] = [
                (sum(prev_bp[k]) / len(prev_bp[k]) * 100.0) if prev_bp[k] else None
                for k in pillar_keys
            ]
            # Delta is null when either window lacks a measured value for the
            # pillar — a delta against a phantom 0 baseline would be misleading.
            delta_arr = [
                (scores_arr[i] - prev_arr[i])
                if scores_arr[i] is not None and prev_arr[i] is not None
                else None
                for i in range(5)
            ]

        version_list = versions_by_key.get(key, [])
        if version_list:
            latest_version = max(version_list, key=lambda x: x[1] or datetime.min.replace(tzinfo=UTC))[0]
            distinct_versions = {v for v, _ in version_list}
            behind = max(0, len(distinct_versions) - 1)
        else:
            latest_version = "unknown"
            behind = 0

        pc = pass_counts.get(key)
        if pc is not None and pc[1] > 0:
            row_pass_rate: float | None = 100.0 * pc[0] / pc[1]
        else:
            row_pass_rate = None

        out_rows.append(
            LeaderboardRow(
                model=model,
                operator=operator,
                trust_tier=_best_trust(trust_by_key.get(key, [])),
                source_commit_sha=shas.get(key, ("", datetime.min.replace(tzinfo=UTC)))[0],
                scores=scores_arr,
                delta=delta_arr,
                runs=len(score_list),
                variance=_stddev([s * 100.0 for s in score_list]),
                cost_per_task=_median(costs.get(key, [])),
                latency_s=_median(latencies_ms.get(key, [])) / 1000.0,
                tokens_total=int(_median([float(t) for t in tokens_by_key.get(key, [])])),
                turns_total=int(_median([float(t) for t in turns_by_key.get(key, [])])),
                sweep_cost=sweep_cost.get(key, 0.0),
                dataset_pin=DatasetPin(version=latest_version, behind=behind),
                tier=row_tier,
                pass_rate=row_pass_rate,
                pillar_counts=counts_arr,
                harness=row_harness,
                effort=row_effort,
            )
        )

    if pillar is not None:
        idx = PILLAR_PARAM_TO_INDEX.get(pillar)
        if idx is None:
            # Should be unreachable — FastAPI Literal validates upstream.
            # Defensive guard against future drift between the route's
            # Literal type and this map.
            raise ValueError(f"Unknown pillar param: {pillar!r}")
        out_rows.sort(
            key=lambda r: (
                -(r.scores[idx] if idx < len(r.scores) and r.scores[idx] is not None else 0.0),
                r.model,
                r.operator,
            )
        )
    else:
        # Rank by the mean of measured pillars only (skip nulls), matching the
        # FE's overall-mean semantics. A row with no measured pillars sorts last.
        def _overall(r: LeaderboardRow) -> float:
            present = [s for s in r.scores if s is not None]
            return sum(present) / len(present) if present else 0.0

        out_rows.sort(key=lambda r: (-_overall(r), r.model, r.operator))

    summary = compute_leaderboard_summary(
        session,
        suites=suites,
        models=models,
        tiers=tiers,
        operators=operators,
        trust=trust,
        dataset_versions=dataset_versions,
        range_days=range_days if range_days and range_days > 0 else 7,
    )

    return LeaderboardResponse(
        rows=out_rows,
        pillars=list(PILLARS),
        summary=summary,
        generated_at=datetime.now(UTC),
    )


def compute_trends_series(
    session: Session,
    *,
    window_days: int,
    show_operators: bool = False,
) -> TrendsSeriesResponse:
    if window_days <= 0:
        return TrendsSeriesResponse(per_model={}, per_operator={}, window_days=0)

    now_ts = datetime.now(UTC)
    cutoff = now_ts - timedelta(days=window_days - 1)
    cutoff_floor = datetime(cutoff.year, cutoff.month, cutoff.day, tzinfo=UTC)

    stmt = (
        select(
            TaskResult.model,
            TaskResult.score_total,
            _date_proxy().label("ts"),
            User.handle,
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        )
        .join(User, User.id == RegisteredRepo.user_id, isouter=True)
        .where(_date_proxy() >= cutoff_floor)
    )

    today = now_ts.date()
    day_index: dict[date, int] = {}
    days_in_order: list[date] = []
    for i in range(window_days):
        d = today - timedelta(days=window_days - 1 - i)
        day_index[d] = i
        days_in_order.append(d)

    model_buckets: dict[str, list[list[float]]] = {}
    operator_buckets: dict[str, list[list[float]]] = {}

    for row in session.exec(stmt).all():
        model, score_total, ts_val, handle = row
        ts = _coalesce_dt(ts_val)
        if ts is None:
            continue
        d = ts.date()
        idx = day_index.get(d)
        if idx is None:
            continue
        score_val = float(score_total or 0.0) * 100.0
        bucket = model_buckets.setdefault(model, [[] for _ in range(window_days)])
        bucket[idx].append(score_val)
        if show_operators:
            op = handle or "self"
            op_bucket = operator_buckets.setdefault(op, [[] for _ in range(window_days)])
            op_bucket[idx].append(score_val)

    # Empty day-buckets are None (gap), NOT 0.0. Plotting 0.0 for a day with
    # no runs drags the line to the x-axis and makes a single real data
    # point look like a flat-at-zero line with an invisible spike. None lets
    # the FE chart render a proper gap / connect across missing days.
    per_model: dict[str, list[float | None]] = {}
    for model, buckets in model_buckets.items():
        per_model[model] = [
            (sum(b) / len(b) if b else None) for b in buckets
        ]
    per_operator: dict[str, list[float | None]] = {}
    if show_operators:
        for op, buckets in operator_buckets.items():
            per_operator[op] = [
                (sum(b) / len(b) if b else None) for b in buckets
            ]

    return TrendsSeriesResponse(
        per_model=per_model,
        per_operator=per_operator,
        window_days=window_days,
    )


def _read_scorers_from_trajectory(traj_path: str) -> list[RowTaskScorerItem]:
    """Read scorer events from a trajectory.jsonl file.

    Scorer events have `event=="scorer"` and carry scorer_name, kind, pass,
    score, detail — written by the runner alongside turn events. Returns []
    when the file is missing, unreadable, or has no scorer events.
    """
    import json as _json
    from pathlib import Path as _Path

    path = _Path(traj_path)
    if not path.exists():
        return []
    items: list[RowTaskScorerItem] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    ev = _json.loads(line)
                except _json.JSONDecodeError:
                    continue
                if ev.get("event") != "scorer":
                    continue
                pass_val = ev.get("pass")
                items.append(
                    RowTaskScorerItem(
                        name=str(ev.get("scorer_name") or ev.get("kind") or ""),
                        pass_=bool(pass_val) if pass_val is not None else None,
                        score=float(ev["score"]) if ev.get("score") is not None else None,
                        detail=ev.get("detail"),
                    )
                )
    except OSError:
        return []
    return items


def compute_row_tasks(
    session: Session,
    *,
    model: str,
    operator: str,
    tier: str,
    harness: str | None = None,
    effort: str | None = None,
) -> list[RowTaskItem]:
    """Per-task drill for a leaderboard row identified by (model, operator, tier).

    harness and effort are optional — when provided, only task-results matching
    those config values are returned. Omitting them applies no filter on those
    dimensions (back-compat with pre-B1 rows where the columns are null).

    Operator matches the same `handle or "self"` logic used by
    compute_leaderboard_response (queries.py:1309). Rows with no RegisteredRepo
    user handle are treated as operator="self" — a direct SQL filter on
    User.handle would exclude those rows, so we apply the operator filter in
    Python after joining.

    Returns one RowTaskItem per distinct task_id, keeping only the most-recent
    task-result (recency = Run.started_at else Submission.ingested_at via
    _date_proxy). Scorers are read from the task-result's trajectory_blob_ref
    (trajectory.jsonl, event=="scorer" lines). Archived-repo rows are excluded
    (same guard as compute_leaderboard_response).
    """
    stmt = (
        select(
            TaskResult.task_id,
            TaskResult.suite,
            TaskResult.passed,
            TaskResult.trajectory_blob_ref,
            _date_proxy().label("ts"),
            User.handle,
        )
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .join(
            RegisteredRepo,
            RegisteredRepo.id == Submission.registered_repo_id,
            isouter=True,
        )
        .join(User, User.id == RegisteredRepo.user_id, isouter=True)
        .where(TaskResult.model == model)
        .where(TaskResult.tier == tier)
        # Replicate the archived-repo exclusion from compute_leaderboard_response.
        .where(
            or_(
                Submission.registered_repo_id.is_(None),
                RegisteredRepo.status != "archived",
            )
        )
    )
    if harness is not None:
        stmt = stmt.where(TaskResult.harness == harness)
    if effort is not None:
        stmt = stmt.where(TaskResult.effort == effort)

    rows = session.exec(stmt).all()

    # Filter to the requested operator: handle or "self" for rows with no handle.
    # This matches the key emitted by compute_leaderboard_response:1309.
    best: dict[str, tuple[datetime | None, Any]] = {}
    for row in rows:
        task_id, suite, passed, traj_ref, ts_val, handle = row
        row_operator = handle or "self"
        if row_operator != operator:
            continue
        ts = _coalesce_dt(ts_val)
        existing = best.get(task_id)
        if existing is None:
            best[task_id] = (ts, row)
            continue
        existing_ts = existing[0]
        # Prefer rows with a timestamp; when both have one keep the later.
        if existing_ts is None or (ts is not None and ts > existing_ts):
            best[task_id] = (ts, row)

    out: list[RowTaskItem] = []
    for task_id in sorted(best):
        _, row = best[task_id]
        _task_id, suite, passed, traj_ref, _ts, _handle = row
        scorers = _read_scorers_from_trajectory(traj_ref) if traj_ref else []
        out.append(
            RowTaskItem(
                task_id=task_id,
                suite=suite or "",
                passed=passed,
                scorers=scorers,
            )
        )
    return out
