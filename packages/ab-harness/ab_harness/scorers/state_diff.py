"""state_diff scorer: union of turn.vault_state_diff lists vs expected sets.

Purely trajectory-driven: run() and replay() are identical.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import replay_unsupported, score_to_verdict
from ab_harness.scorers.assertions import load_events, run_assertion_chain


def _resolve_fixture_dir(task: Task | None) -> Path | None:
    if task is None or not task.fixture_ref:
        return None
    try:
        from ab_cli._discover import fixture_dir_for_task  # type: ignore[import-untyped]
    except ImportError:
        return None
    try:
        return fixture_dir_for_task(task)
    except (RuntimeError, OSError):
        return None


def _collect_state(trajectory_path: Path) -> tuple[set[str], set[str], set[str]]:
    created: set[str] = set()
    modified: set[str] = set()
    deleted: set[str] = set()
    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("event") != "turn":
                continue
            diff = ev.get("vault_state_diff") or {}
            for p in diff.get("created", []) or []:
                created.add(p)
            for p in diff.get("modified", []) or []:
                modified.add(p)
            for p in diff.get("deleted", []) or []:
                deleted.add(p)
    return created, modified, deleted


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a and not b:
        return 1.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 1.0


def state_diff_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    expected_created: list[str] | None = None,
    expected_modified: list[str] | None = None,
    expected_deleted: list[str] | None = None,
    assertions: list[dict[str, Any]] | None = None,
    target_file: str | None = None,
    target_paths: list[str] | None = None,
    scorer_name: str | None = None,
    **_: Any,
) -> ScorerVerdict:
    name = scorer_name or "state_diff"
    kind = ScorerKind.state_diff

    if trajectory_path is None:
        return replay_unsupported(name, kind, "trajectory_path required (state_diff is trajectory-driven)")

    if assertions:
        extra_context: dict[str, Any] = {}
        if target_file:
            extra_context["target_file"] = target_file
        if target_paths:
            extra_context["target_paths"] = target_paths
        return run_assertion_chain(
            name,
            load_events(trajectory_path),
            workdir,
            _resolve_fixture_dir(task),
            assertions,
            extra_context=extra_context,
        )

    exp_created = set(expected_created or [])
    exp_modified = set(expected_modified or [])
    exp_deleted = set(expected_deleted or [])

    got_created, got_modified, got_deleted = _collect_state(trajectory_path)

    missing_created = exp_created - got_created
    missing_modified = exp_modified - got_modified
    missing_deleted = exp_deleted - got_deleted
    unexpected_created = got_created - exp_created if exp_created else set()
    unexpected_modified = got_modified - exp_modified if exp_modified else set()
    unexpected_deleted = got_deleted - exp_deleted if exp_deleted else set()

    missing_any = missing_created or missing_modified or missing_deleted
    ok = not missing_any

    parts: list[float] = []
    if exp_created or got_created:
        parts.append(_jaccard(exp_created, got_created))
    if exp_modified or got_modified:
        parts.append(_jaccard(exp_modified, got_modified))
    if exp_deleted or got_deleted:
        parts.append(_jaccard(exp_deleted, got_deleted))
    score = sum(parts) / len(parts) if parts else 1.0

    detail: dict[str, Any] = {
        "missing": {
            "created": sorted(missing_created),
            "modified": sorted(missing_modified),
            "deleted": sorted(missing_deleted),
        },
        "unexpected": {
            "created": sorted(unexpected_created),
            "modified": sorted(unexpected_modified),
            "deleted": sorted(unexpected_deleted),
        },
    }
    return score_to_verdict(name, kind, ok, score, detail)
