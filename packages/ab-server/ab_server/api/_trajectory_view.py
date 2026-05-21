from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from ab_server.models import (
    RegisteredRepo,
    Submission,
    TaskResult,
)

_CONTENT_CAP_BYTES = 64 * 1024


def _truncate(value: Any) -> tuple[Any, bool]:
    if isinstance(value, (dict, list)):
        try:
            encoded = json.dumps(value, ensure_ascii=False)
        except (TypeError, ValueError):
            encoded = str(value)
        if len(encoded.encode("utf-8")) > _CONTENT_CAP_BYTES:
            return encoded[:_CONTENT_CAP_BYTES], True
        return value, False
    if isinstance(value, str):
        encoded = value.encode("utf-8")
        if len(encoded) > _CONTENT_CAP_BYTES:
            return encoded[:_CONTENT_CAP_BYTES].decode("utf-8", errors="replace"), True
        return value, False
    return value, False


def _normalize_tool_calls(items: Any) -> tuple[list[dict[str, Any]], bool]:
    truncated = False
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out, truncated
    for call in items:
        if not isinstance(call, dict):
            continue
        args, args_trunc = _truncate(call.get("args"))
        if args_trunc:
            truncated = True
        out.append(
            {
                "name": call.get("name"),
                "args": args,
                "truncated": args_trunc,
            }
        )
    return out, truncated


def _normalize_tool_returns(items: Any) -> tuple[list[dict[str, Any]], bool]:
    truncated = False
    out: list[dict[str, Any]] = []
    if not isinstance(items, list):
        return out, truncated
    for ret in items:
        if not isinstance(ret, dict):
            continue
        content_val: Any
        if "content" in ret:
            content_val, c_trunc = _truncate(ret.get("content"))
        else:
            content_val, c_trunc = _truncate({k: v for k, v in ret.items() if k != "path"})
        if c_trunc:
            truncated = True
        out.append(
            {
                "path": ret.get("path"),
                "content": content_val,
                "truncated": c_trunc,
            }
        )
    return out, truncated


def _read_events(traj_path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with traj_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events


def _build_header(run_start: dict[str, Any] | None, run_end: dict[str, Any] | None) -> dict[str, Any]:
    rs = run_start or {}
    re_ = run_end or {}
    return {
        "run_id": rs.get("run_id"),
        "task_id": rs.get("task_id"),
        "model": rs.get("model"),
        "harness": rs.get("harness"),
        "tier": rs.get("tier"),
        "tier_hash": rs.get("tier_hash"),
        "dataset_version": rs.get("dataset_version"),
        "started_at": rs.get("started_at"),
        "finished_at": re_.get("finished_at"),
        "status": re_.get("status"),
        "totals": re_.get("totals"),
    }


def _build_turn(ev: dict[str, Any]) -> dict[str, Any]:
    tool_calls, calls_trunc = _normalize_tool_calls(ev.get("tool_calls"))
    tool_returns, rets_trunc = _normalize_tool_returns(ev.get("tool_returns"))
    model_output, mo_trunc = _truncate(ev.get("model_output", ""))
    return {
        "idx": ev.get("idx", 0),
        "role": ev.get("role"),
        "model_output": model_output,
        "tool_calls": tool_calls,
        "tool_returns": tool_returns,
        "vault_state_diff": ev.get("vault_state_diff"),
        "tokens_in": ev.get("tokens_in", 0),
        "tokens_out": ev.get("tokens_out", 0),
        "latency_ms": ev.get("latency_ms", 0),
        "cost_usd": ev.get("cost_usd", 0.0),
        "truncated": calls_trunc or rets_trunc or mo_trunc,
    }


def _build_scorer(ev: dict[str, Any]) -> dict[str, Any]:
    return {
        "scorer_name": ev.get("scorer_name"),
        "kind": ev.get("kind"),
        "pass": ev.get("pass"),
        "score": ev.get("score"),
        "detail": ev.get("detail"),
    }


def assemble_trajectory_view(
    traj_path: Path,
    *,
    submission: Submission | None = None,
    task_result: TaskResult | None = None,
    repo: RegisteredRepo | None = None,
) -> dict[str, Any]:
    events = _read_events(traj_path)
    run_start: dict[str, Any] | None = None
    run_end: dict[str, Any] | None = None
    turns: list[dict[str, Any]] = []
    scorers: list[dict[str, Any]] = []
    for ev in events:
        kind = ev.get("event")
        if kind == "run_start":
            run_start = ev
        elif kind == "run_end":
            run_end = ev
        elif kind == "turn":
            turns.append(_build_turn(ev))
        elif kind == "scorer":
            scorers.append(_build_scorer(ev))

    header = _build_header(run_start, run_end)

    trust: dict[str, Any] = {
        "tier": submission.trust_tier if submission else "self_reported",
        "re_scored_at": submission.re_scored_at.isoformat() if submission and submission.re_scored_at else None,
        "discrepancy_pct": submission.discrepancy_pct if submission else None,
        "source_commit_sha": submission.source_commit_sha if submission else None,
        "source_path": submission.source_path if submission else None,
        "repo_url": repo.repo_url if repo else None,
    }

    pillars: dict[str, float] | None = None
    if task_result is not None:
        pillars = {
            "correctness": task_result.score_correctness,
            "context_eff": task_result.score_context_eff,
            "tool_skill": task_result.score_tool_skill,
            "memory": task_result.score_memory,
            "latency": task_result.score_latency,
        }

    return {
        "header": header,
        "turns": turns,
        "scorers": scorers,
        "trust": trust,
        "pillars": pillars,
    }


def resolve_submission_paths(
    session: Session,
    submission: Submission,
    fetcher_cache_dir: str,
) -> tuple[Path, RegisteredRepo | None, TaskResult | None]:
    repo = session.get(RegisteredRepo, submission.registered_repo_id)
    clone_dir = Path(fetcher_cache_dir) / str(submission.registered_repo_id)
    traj_path = clone_dir / submission.source_path / "trajectory.jsonl"
    task_result = session.exec(
        select(TaskResult).where(TaskResult.submission_id == submission.id)
    ).first()
    return traj_path, repo, task_result
