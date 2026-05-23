"""Read, write, and validate a results/<utc>-<id>/ run dir."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from statistics import fmean
from typing import Any

from ab_datasets.schemas import ScorerVerdict, Task, Trajectory
from pydantic import BaseModel, ConfigDict, Field

from .manifest import read_metadata, write_metadata

_log = logging.getLogger(__name__)

TRAJECTORY_FILE = "trajectory.jsonl"
SCORES_FILE = "scores.json"
METADATA_FILE = "metadata.yaml"

# The canonical pillar list — must match the keys task YAMLs declare under
# `weights:` (see ab_datasets/schemas/task.py and the build spec §6).
_PILLARS: tuple[str, ...] = (
    "correctness",
    "tool_skill",
    "context_efficiency",
    "latency_cost",
    "memory_specific",
)

# Fallback pillar map. The authoritative map lives in
# `ab_harness.scorers.SCORER_PILLAR_MAP`; we import it lazily inside
# build_scores_payload so ab-sdk does not take a hard dep on ab-harness.
# This constant is the safety net when ab-harness is not installed
# (e.g. server-side validation of an uploaded scores.json).
_FALLBACK_PILLAR_MAP: dict[str, str] = {
    "file_diff": "correctness",
    "schema": "correctness",
    "schema_validator": "correctness",
    "exec": "correctness",
    "readme_exact": "correctness",
    "test_file_unchanged": "correctness",
    "state_diff": "correctness",
    "privacy_check": "correctness",
    "llm_judge": "correctness",
    "tool_skill": "tool_skill",
    "context_efficiency": "context_efficiency",
    "latency_cost": "latency_cost",
    "memory_check": "memory_specific",
    "memory_specific": "memory_specific",
}

_REQUIRED_METADATA_KEYS = (
    "model",
    "tier",
    "dataset_version",
    "started_at",
    "finished_at",
    "harness",
)


class RunDir(BaseModel):
    """Minimal handle to an on-disk run dir."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    path: Path
    run_id: str
    task_id: str
    model: str
    tier: str


class ScoresFile(BaseModel):
    model_config = ConfigDict(extra="allow", populate_by_name=True, protected_namespaces=())

    run_id: str
    task_id: str
    model: str
    tier: str
    dataset_version: str
    verdicts: list[ScorerVerdict] = Field(default_factory=list)
    total_score: float = 0.0
    per_pillar: dict[str, float] = Field(default_factory=dict)
    pass_: bool = Field(default=False, alias="pass")


def _trajectory_to_events(trajectory: Trajectory) -> list[dict[str, Any]]:
    dumped = trajectory.model_dump(mode="json", by_alias=True)
    events: list[dict[str, Any]] = []

    run_start: dict[str, Any] = {
        "event": "run_start",
        "run_id": dumped["run_id"],
        "task_id": dumped["task_id"],
        "model": dumped["model"],
        "harness": dumped["harness"],
        "tier": dumped["tier"],
        "tier_hash": dumped.get("tier_hash"),
        "dataset_version": dumped["dataset_version"],
        "prompt_template_hash": dumped.get("prompt_template_hash"),
        "prompt_label": dumped.get("prompt_label"),
        # system_prompt_verbatim is the verbatim CLAUDE.md / operator prompt
        # text. Serialised here so the publish gate's line-by-line privacy
        # scan (check_publish_ready) covers it before the run goes public.
        "system_prompt_verbatim": dumped.get("system_prompt_verbatim"),
        # isolation records how the runner sandboxed the subprocess (clean-HOME
        # path, fake_home location, bare flag). None for runners that don't
        # record isolation provenance yet.
        "isolation": dumped.get("isolation"),
        "started_at": dumped["started_at"],
    }
    events.append(run_start)

    for turn in dumped.get("turns", []):
        ev = {"event": "turn", **turn}
        events.append(ev)

    for verdict in dumped.get("scorer_verdicts", []):
        ev = {"event": "scorer", **verdict}
        events.append(ev)

    run_end: dict[str, Any] = {
        "event": "run_end",
        "finished_at": dumped.get("finished_at"),
        "status": dumped.get("status"),
        "totals": dumped.get("totals"),
    }
    events.append(run_end)
    return events


def _load_pillar_map() -> dict[str, str]:
    """Try the authoritative map in ab-harness; fall back to the local copy.

    ab-sdk is a lower layer than ab-harness, so we import lazily. In packaged
    environments where ab-harness is not installed (e.g. server-side
    validators), the fallback keeps aggregation working.
    """
    try:
        from ab_harness.scorers import SCORER_PILLAR_MAP  # type: ignore[import-not-found]

        return dict(SCORER_PILLAR_MAP)
    except ImportError:
        return dict(_FALLBACK_PILLAR_MAP)


def _pillar_for(scorer_name: str, pillar_map: dict[str, str]) -> str:
    """Resolve a scorer name to a pillar; unknown scorers default to correctness."""
    return pillar_map.get(scorer_name, "correctness")


def _compute_per_pillar(
    verdicts: list[ScorerVerdict],
    pillar_map: dict[str, str],
) -> dict[str, float]:
    """Group verdicts by pillar; return {pillar: mean(scores)}.

    Pillars with no verdicts are omitted; callers that need a complete
    record per task pillar should consult task.weights and treat missing
    entries as 0.
    """
    buckets: dict[str, list[float]] = {}
    for v in verdicts:
        pillar = _pillar_for(v.scorer_name, pillar_map)
        buckets.setdefault(pillar, []).append(float(v.score))
    return {p: float(fmean(scores)) for p, scores in buckets.items()}


def compute_total_score(
    verdicts: list[ScorerVerdict],
    task: Task | None = None,
) -> tuple[float, dict[str, float]]:
    """Single source of truth for weighted total + per-pillar score.

    Both ``build_scores_payload`` (write path) and the server's rescoring
    engine (read path) must produce the same number when given identical
    verdicts — otherwise the verified trust tier becomes unreachable for
    any task with non-uniform ``weights``.

    Returns ``(total_score, per_pillar)``. ``total_score`` is the weighted
    sum when ``task.weights`` is present; otherwise the unweighted mean of
    verdict scores (backward compatibility).
    """
    pillar_map = _load_pillar_map()
    per_pillar = _compute_per_pillar(verdicts, pillar_map)

    weights: dict[str, float] = dict(task.weights) if task and task.weights else {}

    if weights:
        for pillar, weight in weights.items():
            if float(weight) < 0:
                raise ValueError(
                    f"negative weight not allowed: weights[{pillar!r}]={weight}"
                )
        weight_sum = sum(float(w) for w in weights.values())
        if weight_sum < 1e-9:
            weights = {}  # zero-sum → fall back to unweighted
        # off-by-much is the caller's problem; we proceed silently here
        # (warning logged in build_scores_payload to avoid double-logging).

    if weights:
        total_score = 0.0
        for pillar, weight in weights.items():
            pillar_score = per_pillar.get(pillar, 0.0)
            total_score += float(weight) * float(pillar_score)
    else:
        scores = [v.score for v in verdicts]
        total_score = float(fmean(scores)) if scores else 0.0

    return total_score, per_pillar


def build_scores_payload(
    *,
    run_id: str,
    task_id: str,
    model: str,
    tier: str,
    dataset_version: str,
    verdicts: list[ScorerVerdict],
    task: Task | None = None,
) -> dict[str, Any]:
    """Compute the scores.json dict from a verdict list (single source of truth).

    Aggregation rules:

    * Verdicts are grouped by pillar via ab_harness.scorers.SCORER_PILLAR_MAP
      (with a local fallback). Pillars are: ``correctness``, ``tool_skill``,
      ``context_efficiency``, ``latency_cost``, ``memory_specific``. Each
      pillar's score is the mean of its verdict scores.
    * If ``task`` is given and ``task.weights`` is non-empty, the overall
      ``total_score`` is ``sum(weights[pillar] * pillar_score)``. Pillars
      declared in ``weights`` with no verdict are treated as 0 (missing
      coverage is penalized). Pillars present in verdicts but absent from
      ``weights`` are recorded in ``per_pillar`` but do not contribute to
      ``total_score``.
    * If ``task`` is ``None`` or ``task.weights`` is empty, fall back to the
      legacy unweighted mean of all verdict scores (backward compatible).
    * ``pass`` is True iff every verdict passes AND ``total_score >= 0.5``;
      the second clause is consistent with prior behaviour because the old
      mean was also >= 0.5 exactly when at least half the verdicts passed.

    ``per_pillar`` always reflects the mean of verdict scores per pillar that
    actually saw a verdict; callers that need a fixed-shape record can pad
    with zeros for pillars listed in ``task.weights`` but missing here.
    """
    # Sum-of-weights warning lives here (write path) — once per task.
    if task and task.weights:
        weight_sum = sum(float(w) for w in task.weights.values())
        if weight_sum < 1e-9:
            _log.warning(
                "task.weights sum to zero (task_id=%s); falling back to "
                "unweighted mean",
                task_id,
            )
        elif weight_sum > 1.05 or weight_sum < 0.95:
            _log.warning(
                "task.weights sum to %.4f (task_id=%s); expected ~1.0 — "
                "likely an authoring error, proceeding anyway",
                weight_sum,
                task_id,
            )

    total_score, per_pillar = compute_total_score(verdicts, task)
    all_verdicts_pass = all(v.pass_ for v in verdicts) if verdicts else False
    overall_pass = all_verdicts_pass and total_score >= 0.5

    return {
        "run_id": run_id,
        "task_id": task_id,
        "model": model,
        "tier": tier,
        "dataset_version": dataset_version,
        "verdicts": [v.model_dump(mode="json", by_alias=True) for v in verdicts],
        "total_score": float(total_score),
        "per_pillar": per_pillar,
        "pass": overall_pass,
    }


def _build_scores_payload(
    trajectory: Trajectory,
    verdicts: list[ScorerVerdict],
    task: Task | None = None,
) -> dict[str, Any]:
    tier_val = trajectory.tier.value if hasattr(trajectory.tier, "value") else trajectory.tier
    return build_scores_payload(
        run_id=trajectory.run_id,
        task_id=trajectory.task_id,
        model=trajectory.model,
        tier=str(tier_val),
        dataset_version=trajectory.dataset_version,
        verdicts=verdicts,
        task=task,
    )


def write_run_dir(
    run_dir: Path,
    trajectory: Trajectory,
    metadata: dict[str, Any],
    scorer_verdicts: list[ScorerVerdict] | None = None,
    task: Task | None = None,
) -> None:
    """Write trajectory.jsonl, scores.json, and metadata.yaml into run_dir.

    When ``task`` is supplied, scores.json is aggregated using the task's
    weight pillars (see ``build_scores_payload``). Otherwise the legacy
    unweighted mean is used.
    """
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)

    events = _trajectory_to_events(trajectory)
    with (run_dir / TRAJECTORY_FILE).open("w", encoding="utf-8") as fh:
        for ev in events:
            fh.write(json.dumps(ev, ensure_ascii=False))
            fh.write("\n")

    effective_verdicts = (
        scorer_verdicts if scorer_verdicts is not None else list(trajectory.scorer_verdicts)
    )
    payload = _build_scores_payload(trajectory, effective_verdicts, task=task)
    with (run_dir / SCORES_FILE).open("w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    tier_val = trajectory.tier.value if hasattr(trajectory.tier, "value") else trajectory.tier
    status_val = (
        trajectory.status.value
        if trajectory.status is not None and hasattr(trajectory.status, "value")
        else trajectory.status
    )
    enriched = dict(metadata)
    enriched.setdefault("run_id", trajectory.run_id)
    enriched.setdefault("task_id", trajectory.task_id)
    enriched.setdefault("model", trajectory.model)
    enriched.setdefault("tier", tier_val)
    enriched.setdefault("tier_hash", trajectory.tier_hash)
    enriched.setdefault("dataset_version", trajectory.dataset_version)
    enriched.setdefault("harness", trajectory.harness)
    enriched.setdefault(
        "started_at",
        trajectory.started_at.isoformat() if trajectory.started_at else None,
    )
    enriched.setdefault(
        "finished_at",
        trajectory.finished_at.isoformat() if trajectory.finished_at else None,
    )
    enriched.setdefault("status", status_val)
    enriched.setdefault("prompt_template_hash", trajectory.prompt_template_hash)
    enriched.setdefault("prompt_label", trajectory.prompt_label)
    write_metadata(run_dir / METADATA_FILE, enriched)


def read_run_dir(run_dir: Path) -> RunDir:
    """Parse metadata.yaml and return a RunDir handle."""
    run_dir = Path(run_dir)
    meta = read_metadata(run_dir / METADATA_FILE)
    try:
        return RunDir(
            path=run_dir,
            run_id=str(meta["run_id"]),
            task_id=str(meta["task_id"]),
            model=str(meta["model"]),
            tier=str(meta["tier"]),
        )
    except KeyError as exc:
        raise ValueError(f"metadata.yaml missing required field: {exc.args[0]}") from exc


def read_trajectory(run_dir: Path) -> Trajectory:
    """Read trajectory.jsonl and reconstruct a Trajectory model."""
    run_dir = Path(run_dir)
    path = run_dir / TRAJECTORY_FILE

    events: list[dict[str, Any]]
    try:
        from ab_harness.trajectory.reader import TrajectoryReader  # type: ignore[import-not-found]

        events = list(TrajectoryReader(path))
    except ImportError:
        events = _iter_events_manual(path)

    return _reconstruct_trajectory(path, events)


def read_scores(run_dir: Path) -> ScoresFile:
    """Read scores.json and validate against ScoresFile schema."""
    run_dir = Path(run_dir)
    with (run_dir / SCORES_FILE).open("r", encoding="utf-8") as fh:
        data = json.load(fh)
    return ScoresFile.model_validate(data)


def _iter_events_manual(path: Path) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line = raw.strip()
            if not line:
                continue
            events.append(json.loads(line))
    return events


def _reconstruct_trajectory(path: Path, events: list[dict[str, Any]]) -> Trajectory:
    run_start: dict[str, Any] | None = None
    run_end: dict[str, Any] | None = None
    turns: list[dict[str, Any]] = []
    scorers: list[dict[str, Any]] = []

    for ev in events:
        kind = ev.get("event")
        if kind == "run_start":
            run_start = ev
        elif kind == "turn":
            turns.append({k: v for k, v in ev.items() if k != "event"})
        elif kind == "scorer":
            scorers.append({k: v for k, v in ev.items() if k != "event"})
        elif kind == "run_end":
            run_end = ev

    if run_start is None:
        raise ValueError(f"trajectory missing run_start: {path}")
    if run_end is None:
        raise ValueError(f"trajectory missing run_end: {path}")

    payload: dict[str, Any] = {
        "run_id": run_start.get("run_id"),
        "task_id": run_start.get("task_id"),
        "model": run_start.get("model"),
        "harness": run_start.get("harness"),
        "tier": run_start.get("tier"),
        "tier_hash": run_start.get("tier_hash"),
        "dataset_version": run_start.get("dataset_version"),
        "prompt_template_hash": run_start.get("prompt_template_hash"),
        "prompt_label": run_start.get("prompt_label"),
        "system_prompt_verbatim": run_start.get("system_prompt_verbatim"),
        "isolation": run_start.get("isolation"),
        "started_at": run_start.get("started_at"),
        "finished_at": run_end.get("finished_at"),
        "status": run_end.get("status"),
        "turns": turns,
        "scorer_verdicts": scorers,
        "totals": run_end.get("totals"),
    }
    return Trajectory.model_validate(payload)


def validate(run_dir: Path, *, require_privacy_pass: bool = False) -> list[str]:
    """Return a list of issues with the run dir; empty list means valid."""
    run_dir = Path(run_dir)
    issues: list[str] = []

    for fname in (TRAJECTORY_FILE, SCORES_FILE, METADATA_FILE):
        if not (run_dir / fname).exists():
            issues.append(f"missing file: {fname}")

    traj_path = run_dir / TRAJECTORY_FILE
    if traj_path.exists():
        issues.extend(_validate_trajectory(traj_path))

    scores_path = run_dir / SCORES_FILE
    scores_data: dict[str, Any] | None = None
    if scores_path.exists():
        try:
            with scores_path.open("r", encoding="utf-8") as fh:
                scores_data = json.load(fh)
        except json.JSONDecodeError as exc:
            issues.append(f"scores.json: invalid JSON ({exc.msg})")
        else:
            try:
                ScoresFile.model_validate(scores_data)
            except Exception as exc:
                issues.append(f"scores.json: schema validation failed ({exc})")

    meta_path = run_dir / METADATA_FILE
    if meta_path.exists():
        try:
            meta = read_metadata(meta_path)
        except Exception as exc:
            issues.append(f"metadata.yaml: cannot read ({exc})")
        else:
            for key in _REQUIRED_METADATA_KEYS:
                if key not in meta:
                    issues.append(f"metadata.yaml: missing required key {key!r}")

    if require_privacy_pass:
        if scores_data is None:
            issues.append("privacy gate: scores.json missing or invalid; cannot verify privacy_check")
        else:
            verdicts = scores_data.get("verdicts") or scores_data.get("scorer_verdicts") or []
            passed = False
            for v in verdicts:
                name = v.get("scorer_name") or v.get("name")
                ok = v.get("pass") if "pass" in v else v.get("pass_")
                if name == "privacy_check" and bool(ok):
                    passed = True
                    break
            if not passed:
                issues.append("privacy gate: no passing privacy_check verdict in scores.json")

    return issues


def _validate_trajectory(traj_path: Path) -> list[str]:
    issues: list[str] = []
    try:
        from ab_harness.trajectory.validate import (  # type: ignore[import-not-found]
            validate as harness_validate,
        )
    except ImportError:
        harness_validate = None  # type: ignore[assignment]

    if harness_validate is not None:
        try:
            return list(harness_validate(traj_path))
        except Exception as exc:
            issues.append(f"trajectory.jsonl: harness validate raised ({exc})")

    run_start_count = 0
    run_end_count = 0
    last_turn_idx = -1
    with traj_path.open("r", encoding="utf-8") as fh:
        for lineno, raw in enumerate(fh, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError as exc:
                issues.append(f"trajectory.jsonl line {lineno}: invalid JSON ({exc.msg})")
                continue
            kind = ev.get("event")
            if kind == "run_start":
                run_start_count += 1
            elif kind == "run_end":
                run_end_count += 1
            elif kind == "turn":
                idx = ev.get("idx")
                if not isinstance(idx, int) or idx != last_turn_idx + 1:
                    issues.append(
                        f"trajectory.jsonl line {lineno}: turn idx {idx!r} not monotonic"
                    )
                if isinstance(idx, int):
                    last_turn_idx = idx
    if run_start_count != 1:
        issues.append(
            f"trajectory.jsonl must have exactly one run_start (got {run_start_count})"
        )
    if run_end_count != 1:
        issues.append(
            f"trajectory.jsonl must have exactly one run_end (got {run_end_count})"
        )
    return issues


__all__ = [
    "METADATA_FILE",
    "SCORES_FILE",
    "TRAJECTORY_FILE",
    "RunDir",
    "ScorerVerdict",
    "ScoresFile",
    "build_scores_payload",
    "read_run_dir",
    "read_scores",
    "read_trajectory",
    "validate",
    "write_run_dir",
]
