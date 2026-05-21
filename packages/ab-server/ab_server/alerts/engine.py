"""Alert rule evaluation.

`evaluate_alert(session, rule)` decides whether an `AlertRule` should fire right
now. It compares the mean of the rule's metric in the current window vs the
mean in the prior window of the same length. If the relative delta in the
configured direction exceeds `threshold_pct`, the alert fires.

`last_evaluated_at` is updated on every call. `last_fired_at` is updated only
when the rule fires.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import case, select
from sqlmodel import Session

from ab_server.models.alert import AlertRule
from ab_server.models.run import Run
from ab_server.models.submission import Submission
from ab_server.models.task_result import TaskResult

_ALLOWED_METRICS = {
    "score_total",
    "score_correctness",
    "score_context_eff",
    "score_tool_skill",
    "score_memory",
    "score_latency",
    "cost_usd",
    "latency_ms",
}


def _metric_column(metric: str):
    if metric not in _ALLOWED_METRICS:
        raise ValueError(f"unsupported metric: {metric!r}")
    return getattr(TaskResult, metric)


def _date_proxy():
    return case(
        (Run.started_at.is_not(None), Run.started_at),
        else_=Submission.ingested_at,
    )


def _collect_window_means(
    session: Session,
    *,
    metric: str,
    suite: str | None,
    model: str | None,
    tier: str | None,
    window_days: int,
    now: datetime,
) -> tuple[float | None, float | None, int, int]:
    """Return (current_mean, prev_mean, n_current, n_prev).

    Current window: [now - window_days, now].
    Prior window: [now - 2*window_days, now - window_days].
    """
    metric_col = _metric_column(metric)
    floor = now - timedelta(days=2 * window_days)
    current_floor = now - timedelta(days=window_days)

    stmt = (
        select(metric_col, _date_proxy().label("ts"))
        .select_from(TaskResult)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .join(Run, Run.id == TaskResult.run_id, isouter=True)
        .where(_date_proxy() >= floor)
    )
    if suite:
        stmt = stmt.where(TaskResult.suite == suite)
    if model:
        stmt = stmt.where(TaskResult.model == model)
    if tier:
        stmt = stmt.where(TaskResult.tier == tier)

    cur: list[float] = []
    prev: list[float] = []
    for value, ts_val in session.exec(stmt).all():
        if ts_val is None:
            continue
        ts = ts_val if isinstance(ts_val, datetime) else None
        if ts is None:
            continue
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        v = float(value or 0.0)
        if ts >= current_floor:
            cur.append(v)
        else:
            prev.append(v)

    cur_mean = sum(cur) / len(cur) if cur else None
    prev_mean = sum(prev) / len(prev) if prev else None
    return cur_mean, prev_mean, len(cur), len(prev)


def _delta_pct(cur: float, prev: float) -> float:
    """Relative change current vs prior, as percentage (cur - prev) / |prev| * 100.

    If prev is 0, fall back to absolute delta * 100 so the threshold is still
    meaningful for fractional-score metrics (which are bounded 0..1).
    """
    if prev == 0:
        return (cur - prev) * 100.0
    return (cur - prev) / abs(prev) * 100.0


def evaluate_alert(
    session: Session,
    rule: AlertRule,
    *,
    now: datetime | None = None,
    commit: bool = True,
) -> bool:
    """Evaluate the rule. Updates last_evaluated_at always; last_fired_at on fire.

    Returns True if the alert fires, False otherwise.
    """
    now = now or datetime.now(UTC)

    if not rule.enabled:
        rule.last_evaluated_at = now
        if commit:
            session.add(rule)
            session.commit()
            session.refresh(rule)
        return False

    cur_mean, prev_mean, n_cur, n_prev = _collect_window_means(
        session,
        metric=rule.metric,
        suite=rule.suite,
        model=rule.model,
        tier=rule.tier,
        window_days=rule.window_days,
        now=now,
    )

    fired = False
    if cur_mean is not None and prev_mean is not None and n_cur > 0 and n_prev > 0:
        delta = _delta_pct(cur_mean, prev_mean)
        threshold = abs(rule.threshold_pct)
        if (rule.direction == "down" and delta <= -threshold) or (rule.direction == "up" and delta >= threshold):
            fired = True

    rule.last_evaluated_at = now
    if fired:
        rule.last_fired_at = now

    if commit:
        session.add(rule)
        session.commit()
        session.refresh(rule)
    return fired


def evaluate_all(
    session: Session,
    rules: Sequence[AlertRule],
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Evaluate a list of rules. Returns {evaluated: N, fired: [rules]}."""
    now = now or datetime.now(UTC)
    fired: list[AlertRule] = []
    for rule in rules:
        if evaluate_alert(session, rule, now=now, commit=False):
            fired.append(rule)
        session.add(rule)
    session.commit()
    for r in rules:
        session.refresh(r)
    return {"evaluated": len(rules), "fired": fired}
