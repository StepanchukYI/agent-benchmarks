"""JSON Schema validator scorer."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema
from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import replay_unsupported, score_to_verdict


def _load_schema(
    schema: dict[str, Any] | None,
    schema_path: str | Path | None,
    workdir: Path | None,
) -> dict[str, Any] | str:
    if schema is not None:
        return schema
    if schema_path is None:
        return "no schema provided (need `schema` or `schema_path`)"
    p = Path(schema_path)
    if not p.is_absolute() and workdir is not None:
        p = workdir / p
    if not p.exists():
        return f"schema_path not found: {p}"
    return json.loads(p.read_text(encoding="utf-8"))


def _load_target_from_workdir(
    workdir: Path,
    target: str,
) -> tuple[Any, str | None]:
    p = workdir / target
    if not p.exists():
        return None, f"target file not found: {target}"
    try:
        return json.loads(p.read_text(encoding="utf-8")), None
    except json.JSONDecodeError as exc:
        return None, f"target is not valid JSON: {exc}"


def _load_target_from_trajectory(
    trajectory_path: Path,
    target: str,
) -> tuple[Any, str | None]:
    last_content: str | None = None
    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            ev = json.loads(line)
            if ev.get("event") != "turn":
                continue
            diff = ev.get("vault_state_diff") or {}
            if target in (diff.get("deleted") or []):
                last_content = None
            for ret in ev.get("tool_returns", []) or []:
                if not isinstance(ret, dict):
                    continue
                if ret.get("path") == target and isinstance(ret.get("content"), str):
                    last_content = ret["content"]

    if last_content is None:
        return None, f"target {target!r} content not reconstructable from trajectory"
    try:
        return json.loads(last_content), None
    except json.JSONDecodeError as exc:
        return None, f"reconstructed target is not valid JSON: {exc}"


def schema_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    target: str | None = None,
    schema: dict[str, Any] | None = None,
    schema_path: str | Path | None = None,
    **_: Any,
) -> ScorerVerdict:
    name = "schema"
    kind = ScorerKind.schema

    if target is None:
        return score_to_verdict(name, kind, False, 0.0, {"error": "`target` is required"})

    if mode == "replay" or workdir is None:
        if trajectory_path is None:
            return replay_unsupported(name, kind, "trajectory_path required for replay")
        instance, err = _load_target_from_trajectory(trajectory_path, target)
    else:
        instance, err = _load_target_from_workdir(workdir, target)

    if err:
        return score_to_verdict(name, kind, False, 0.0, {"error": err})

    loaded = _load_schema(schema, schema_path, workdir)
    if isinstance(loaded, str):
        return score_to_verdict(name, kind, False, 0.0, {"error": loaded})

    validator = jsonschema.Draft202012Validator(loaded)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    if not errors:
        return score_to_verdict(name, kind, True, 1.0, {"errors": []})

    detail = {
        "errors": [
            {
                "path": list(e.absolute_path),
                "message": e.message,
                "validator": e.validator,
            }
            for e in errors[:3]
        ],
        "total_errors": len(errors),
    }
    return score_to_verdict(name, kind, False, 0.0, detail)
