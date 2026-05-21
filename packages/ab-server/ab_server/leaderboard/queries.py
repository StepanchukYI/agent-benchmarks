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

from sqlalchemy import case, func
from sqlmodel import Session, select

from ab_server.models.repo import RegisteredRepo
from ab_server.models.run import Run
from ab_server.models.submission import Submission
from ab_server.models.task_result import TaskResult
from ab_server.models.user import User

from .schemas import (
    CIGateStatus,
    DatasetPin,
    LeaderboardCell,
    LeaderboardMatrix,
    LeaderboardMatrixRow,
    LeaderboardResponse,
    LeaderboardRow,
    ParetoPoint,
    ParetoSeries,
    RegressionItem,
    RegressionsPanel,
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

    return TrendsOverview(
        window_days=window_days,
        active_regressions_count=len(down.items),
        improvements_count=len(up.items),
        ci_gate_status=status,
        ci_gate_blocked_merges_48h=blocked,
        alerts_count_window=0,
        alerts_actioned=0,
        last_full_sweep_at=_last_full_sweep_at(session),
        last_full_sweep_cadence="scheduled · 03:00 daily",
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


def _mode(values: Sequence[str], default: str) -> str:
    if not values:
        return default
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return max(counts.items(), key=lambda kv: kv[1])[0]


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
            Submission.trust_tier,
            Submission.source_commit_sha,
            Submission.dataset_version,
            Submission.ingested_at,
            Run.dataset_version,
            Run.started_at,
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

    Bucket = tuple[str, str]
    pillar_keys = ("correctness", "context_eff", "tool_skill", "memory", "latency")
    scores: dict[Bucket, list[float]] = {}
    pillars_by_key: dict[Bucket, dict[str, list[float]]] = {}
    costs: dict[Bucket, list[float]] = {}
    latencies_ms: dict[Bucket, list[float]] = {}
    suites_seen: dict[Bucket, list[str]] = {}
    tasks_seen: dict[Bucket, set[tuple[str, str]]] = {}
    sweep_cost: dict[Bucket, float] = {}
    trust_by_key: dict[Bucket, list[str]] = {}
    tiers_by_key: dict[Bucket, list[str]] = {}
    shas: dict[Bucket, tuple[str, datetime]] = {}
    versions_by_key: dict[Bucket, list[tuple[str, datetime | None]]] = {}

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
            trust_tier,
            commit_sha,
            sub_dataset_version,
            ingested_at,
            run_dataset_version,
            started_at,
            handle,
        ) = row

        operator = handle or "self"
        key: Bucket = (model, operator)
        scores.setdefault(key, []).append(float(score_total or 0.0))
        bucket_pillars = pillars_by_key.setdefault(
            key, {k: [] for k in pillar_keys}
        )
        bucket_pillars["correctness"].append(float(s_corr or 0.0))
        bucket_pillars["context_eff"].append(float(s_ctx or 0.0))
        bucket_pillars["tool_skill"].append(float(s_tool or 0.0))
        bucket_pillars["memory"].append(float(s_mem or 0.0))
        bucket_pillars["latency"].append(float(s_lat or 0.0))
        costs.setdefault(key, []).append(float(cost_usd or 0.0))
        latencies_ms.setdefault(key, []).append(float(latency_ms or 0))
        suites_seen.setdefault(key, []).append(suite)
        tasks_seen.setdefault(key, set()).add((task_id, suite))
        tiers_by_key.setdefault(key, []).append(tier)
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
        model_p, c_p, ctx_p, tool_p, mem_p, lat_p, handle_p = prow
        kp: Bucket = (model_p, handle_p or "self")
        bp = prev_pillars.setdefault(kp, {k: [] for k in pillar_keys})
        bp["correctness"].append(float(c_p or 0.0))
        bp["context_eff"].append(float(ctx_p or 0.0))
        bp["tool_skill"].append(float(tool_p or 0.0))
        bp["memory"].append(float(mem_p or 0.0))
        bp["latency"].append(float(lat_p or 0.0))

    out_rows: list[LeaderboardRow] = []
    for key, score_list in scores.items():
        model, operator = key
        bucket_pillars = pillars_by_key.get(key, {k: [] for k in pillar_keys})
        scores_arr = [
            (sum(bucket_pillars[k]) / len(bucket_pillars[k]) if bucket_pillars[k] else 0.0) * 100.0
            for k in pillar_keys
        ]
        prev_bp = prev_pillars.get(key)
        if prev_bp is None:
            delta_arr = [0.0] * 5
        else:
            prev_arr = [
                (sum(prev_bp[k]) / len(prev_bp[k]) if prev_bp[k] else 0.0) * 100.0
                for k in pillar_keys
            ]
            delta_arr = [scores_arr[i] - prev_arr[i] for i in range(5)]

        version_list = versions_by_key.get(key, [])
        if version_list:
            latest_version = max(version_list, key=lambda x: x[1] or datetime.min.replace(tzinfo=UTC))[0]
            distinct_versions = {v for v, _ in version_list}
            behind = max(0, len(distinct_versions) - 1)
        else:
            latest_version = "unknown"
            behind = 0

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
                sweep_cost=sweep_cost.get(key, 0.0),
                dataset_pin=DatasetPin(version=latest_version, behind=behind),
                tier=_mode(tiers_by_key.get(key, []), "T0"),
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
                -(r.scores[idx] if idx < len(r.scores) else 0.0),
                r.model,
                r.operator,
            )
        )
    else:
        out_rows.sort(key=lambda r: (-sum(r.scores) / 5.0, r.model, r.operator))
    return LeaderboardResponse(
        rows=out_rows,
        pillars=list(PILLARS),
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

    per_model: dict[str, list[float]] = {}
    for model, buckets in model_buckets.items():
        per_model[model] = [
            (sum(b) / len(b) if b else 0.0) for b in buckets
        ]
    per_operator: dict[str, list[float]] = {}
    if show_operators:
        for op, buckets in operator_buckets.items():
            per_operator[op] = [
                (sum(b) / len(b) if b else 0.0) for b in buckets
            ]

    return TrendsSeriesResponse(
        per_model=per_model,
        per_operator=per_operator,
        window_days=window_days,
    )
