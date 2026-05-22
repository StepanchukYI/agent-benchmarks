from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from statistics import median
from typing import Annotated, Any

import ab_datasets
import yaml
from ab_datasets.loaders import load_task
from ab_datasets.schemas import Task
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from ab_server.db import get_session
from ab_server.models import Submission, TaskResult

router = APIRouter(tags=["datasets"])


def _datasets_root() -> Path:
    """Resolve the ab_datasets package directory.

    Prefer the installed package; fall back to repo-relative via AB_REPO_ROOT.
    """
    pkg = Path(ab_datasets.__file__).resolve().parent
    if (pkg / "L0_foundation").is_dir():
        return pkg
    env_root = os.environ.get("AB_REPO_ROOT")
    if env_root:
        candidate = Path(env_root) / "packages" / "ab-datasets" / "ab_datasets"
        if candidate.is_dir():
            return candidate
    return pkg


def _fixtures_root() -> Path:
    pkg = Path(ab_datasets.__file__).resolve().parent
    sibling = pkg.parent / "fixtures"
    if sibling.is_dir():
        return sibling
    env_root = os.environ.get("AB_REPO_ROOT")
    if env_root:
        candidate = Path(env_root) / "packages" / "ab-datasets" / "fixtures"
        if candidate.is_dir():
            return candidate
    return sibling


def _walk_task_files() -> list[Path]:
    ds = _datasets_root()
    out: list[Path] = []
    if not ds.exists():
        return out
    for layer_dir in sorted(ds.iterdir()):
        if not layer_dir.is_dir() or not layer_dir.name.startswith("L"):
            continue
        out.extend(sorted(layer_dir.rglob("*.yaml")))
    return out


def _safe_load_task(path: Path) -> Task | None:
    try:
        return load_task(path)
    except Exception:
        return None


def _task_to_summary(task: Task) -> dict[str, Any]:
    has_fixtures = False
    if task.fixture_ref:
        fixtures = _fixtures_root()
        repo_relative = fixtures.parent.parent.parent / task.fixture_ref
        if (
            (fixtures.parent / task.fixture_ref).exists()
            or (fixtures / task.fixture_ref).exists()
            or repo_relative.exists()
        ):
            has_fixtures = True
    return {
        "id": task.id,
        "layer": str(task.layer),
        "suite": task.suite,
        "title": task.title,
        "difficulty": str(task.difficulty),
        "required_tier": task.config.required_tier,
        "trust_tier_ceiling": str(task.trust_tier_ceiling),
        "has_fixtures": has_fixtures,
    }


def _task_to_detail(task: Task) -> dict[str, Any]:
    return {
        "id": task.id,
        "layer": str(task.layer),
        "suite": task.suite,
        "title": task.title,
        "description": task.description,
        "difficulty": str(task.difficulty),
        "required_tier": task.config.required_tier,
        "recommended_tier": task.config.recommended_tier,
        "also_run_on": list(task.config.also_run_on),
        "requires": dict(task.config.requires),
        "trust_tier_ceiling": str(task.trust_tier_ceiling),
        "visibility": str(task.visibility),
        "fixture_ref": task.fixture_ref,
        "acceptance_criteria": list(task.acceptance_criteria),
        "weights": dict(task.weights),
        "scorer_chain": [
            {"name": s.name, "kind": str(s.kind), "config": dict(s.config)}
            for s in task.scorer_chain
        ],
        "tags": list(task.tags),
    }


def _runs_count_by_task(
    session: Session, since: datetime
) -> dict[str, int]:
    out: dict[str, int] = {}
    stmt = (
        select(TaskResult.task_id, Submission.ingested_at)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
    )
    for task_id, ingested_at in session.exec(stmt).all():
        ts = _ensure_utc(ingested_at)
        if ts is None or ts < since:
            continue
        out[task_id] = out.get(task_id, 0) + 1
    return out


def _ensure_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    return None


def _compute_task_stats(session: Session, task_id: str) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    rows = session.exec(
        select(TaskResult, Submission.ingested_at)
        .join(Submission, Submission.id == TaskResult.submission_id, isouter=True)
        .where(TaskResult.task_id == task_id)
    ).all()
    within: list[tuple[TaskResult, datetime]] = []
    for tr, ingested in rows:
        ts = _ensure_utc(ingested)
        if ts is None or ts < cutoff:
            continue
        within.append((tr, ts))

    runs_count = len(within)
    if runs_count == 0:
        return {
            "runs_count_30d": 0,
            "pass_rate_30d": None,
            "median_cost_usd": None,
            "median_latency_ms": None,
            "median_turns": None,
        }

    passed = sum(
        1 for tr, _ in within if tr.status == "completed" and tr.score_total >= 0.99
    )
    pass_rate = passed / runs_count
    costs = [tr.cost_usd for tr, _ in within]
    latencies = [tr.latency_ms for tr, _ in within]
    turns = [tr.turns_total for tr, _ in within if tr.turns_total]
    return {
        "runs_count_30d": runs_count,
        "pass_rate_30d": pass_rate,
        "median_cost_usd": median(costs) if costs else None,
        "median_latency_ms": median(latencies) if latencies else None,
        "median_turns": median(turns) if turns else None,
    }


@router.get("/tasks")
def list_tasks(
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    cutoff = datetime.now(UTC) - timedelta(days=30)
    counts = _runs_count_by_task(session, cutoff)
    items: list[dict[str, Any]] = []
    for path in _walk_task_files():
        task = _safe_load_task(path)
        if task is None:
            continue
        summary = _task_to_summary(task)
        summary["runs_count_30d"] = counts.get(task.id, 0)
        items.append(summary)
    return {"items": items, "count": len(items)}


@router.get("/tasks/{id}")
def get_task(
    id: str,
    session: Annotated[Session, Depends(get_session)],
) -> dict[str, Any]:
    target: Task | None = None
    for path in _walk_task_files():
        task = _safe_load_task(path)
        if task is None:
            continue
        if task.id == id:
            target = task
            break
    if target is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"task {id} not found"
        )
    detail = _task_to_detail(target)
    detail["stats"] = _compute_task_stats(session, id)
    return detail


def _load_tier_manifest(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    return data


@router.get("/tiers")
def list_tiers() -> dict[str, Any]:
    root = _fixtures_root() / "config_tiers"
    items: list[dict[str, Any]] = []
    if not root.exists():
        return {"items": items, "count": 0}
    for tier_dir in sorted(root.iterdir()):
        if not tier_dir.is_dir():
            continue
        manifest_path = tier_dir / "manifest.yaml"
        data = _load_tier_manifest(manifest_path)
        if data is None:
            continue
        skills = data.get("skills") or []
        mcps = data.get("mcps") or []
        claude_md = data.get("claude_md")
        vault_state = data.get("vault_state")
        items.append(
            {
                "name": data.get("tier") or tier_dir.name,
                "directory": tier_dir.name,
                "description": data.get("description", ""),
                "claude_md_present": bool(claude_md),
                "skills_count": len(skills) if isinstance(skills, list) else 0,
                "mcps_count": len(mcps) if isinstance(mcps, list) else 0,
                "vault_snapshot": (
                    vault_state.get("snapshot") if isinstance(vault_state, dict) else None
                ),
            }
        )
    return {"items": items, "count": len(items)}
