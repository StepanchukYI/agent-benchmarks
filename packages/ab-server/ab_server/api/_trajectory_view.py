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


_READ_HINTS = ("read", "cat", "grep", "search", "list", "glob", "find", "view")
_WRITE_HINTS = ("write", "edit", "create", "patch", "apply", "save", "put", "modify", "delete")


def _first_tool_call_name(ev: dict[str, Any]) -> str | None:
    calls = ev.get("tool_calls") or []
    if not isinstance(calls, list) or not calls:
        return None
    head = calls[0]
    if isinstance(head, dict):
        name = head.get("name")
        if isinstance(name, str):
            return name
    return None


def _tool_label(ev: dict[str, Any]) -> str:
    calls = ev.get("tool_calls") or []
    if not isinstance(calls, list) or not calls:
        return "tool"
    parts: list[str] = []
    for call in calls:
        if not isinstance(call, dict):
            continue
        name = call.get("name") or "tool"
        args = call.get("args")
        primary_arg: str | None = None
        if isinstance(args, dict):
            for k in ("path", "file_path", "filename", "target", "query"):
                v = args.get(k)
                if isinstance(v, str) and v:
                    primary_arg = v
                    break
        parts.append(f"{name}({primary_arg})" if primary_arg else name)
    return ", ".join(parts[:3])


def _turn_kind_and_icon(ev: dict[str, Any], idx: int) -> tuple[str, str]:
    """Classify a turn into designer's TurnEvent.kind + lucide icon."""
    role = ev.get("role")
    if role == "user":
        return ("prompt", "user") if idx == 0 else ("thought", "brain")
    if role == "tool":
        return ("tool", "cube")
    if role == "assistant":
        tool_name = _first_tool_call_name(ev)
        if tool_name is None:
            return ("thought", "brain")
        lowered = tool_name.lower()
        if any(h in lowered for h in _WRITE_HINTS):
            return ("write", "pencil")
        if any(h in lowered for h in _READ_HINTS):
            return ("read", "file-text")
        return ("tool", "cube")
    return ("thought", "brain")


def _turn_meta(ev: dict[str, Any]) -> str:
    """Compact subtext (tokens · latency)."""
    tokens_out = ev.get("tokens_out", 0)
    latency_ms = ev.get("latency_ms", 0)
    parts: list[str] = []
    if tokens_out:
        parts.append(f"tokens {int(tokens_out)}")
    if latency_ms:
        parts.append(f"{int(latency_ms)} ms")
    return " · ".join(parts) if parts else ""


def _turn_to_event(ev: dict[str, Any], idx: int) -> dict[str, Any]:
    kind, icon = _turn_kind_and_icon(ev, idx)
    if kind in {"tool", "read", "write"}:
        label = _tool_label(ev)
    elif kind == "prompt":
        label = "System prompt + task"
    else:
        text = ev.get("model_output") or ""
        if isinstance(text, str):
            stripped = text.strip().splitlines()[0] if text.strip() else "thought"
            label = stripped[:80]
        else:
            label = "thought"
    return {
        "idx": ev.get("idx", idx),
        "role": ev.get("role"),
        "kind": kind,
        "label": label,
        "meta": _turn_meta(ev),
        "icon": icon,
    }


def _scorer_to_event(ev: dict[str, Any], idx_offset: int) -> dict[str, Any]:
    raw_kind = ev.get("kind") or ""
    is_judge = raw_kind == "llm_judge"
    name = ev.get("scorer_name") or raw_kind or "scorer"
    score = ev.get("score")
    pass_ = ev.get("pass")
    if isinstance(score, (int, float)):
        meta = f"score {score:.2f}"
    elif pass_ is not None:
        meta = "pass" if pass_ else "fail"
    else:
        meta = ""
    return {
        "idx": idx_offset,
        "role": "system",
        "kind": "judge" if is_judge else "verdict",
        "label": f"LLM-judge: {name}" if is_judge else f"Scorer: {name}",
        "meta": meta,
        "icon": "scale" if is_judge else "check-circle-2",
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
    designer_events: list[dict[str, Any]] = []
    turn_idx_counter = 0
    for ev in events:
        kind = ev.get("event")
        if kind == "run_start":
            run_start = ev
        elif kind == "run_end":
            run_end = ev
        elif kind == "turn":
            turns.append(_build_turn(ev))
            designer_events.append(_turn_to_event(ev, turn_idx_counter))
            turn_idx_counter += 1
        elif kind == "scorer":
            scorers.append(_build_scorer(ev))
            designer_events.append(_scorer_to_event(ev, turn_idx_counter))
            turn_idx_counter += 1

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
        "events": designer_events,
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
