"""JSON Schema / JSON-value validator scorer.

Supports three comparison modes (driven by YAML's ``mode``):

* ``mode: "schema"`` (legacy default) — validate the loaded JSON instance
  against ``schema`` (inline) or ``schema_path`` (file). Produces a verdict
  with the first 3 ``jsonschema`` errors on failure.
* ``mode: "exact_json"`` — same as schema mode; alias surfaced for clarity
  when the YAML's intent is "the final structured output MUST match this
  schema exactly". Same fields apply (``schema`` / ``schema_path``).
* ``mode: "json_value_equals"`` — deep-equality compare the loaded value
  against ``expected``. Optional ``additional_properties_forbidden: true``
  makes extra dict keys fail.

Two input sources (driven by YAML's ``input``):

* ``input: "file"`` (default) — read JSON from ``workdir/<target>`` (run)
  or reconstruct from trajectory (replay).
* ``input: "final_assistant_message"`` — pull the final assistant turn's
  ``model_output`` from the trajectory and parse it as JSON. Works in both
  run and replay modes because the trajectory is always written.

The harness run/replay signal arrives via the ``mode`` kwarg too, but only
when the YAML doesn't set ``mode`` (see ab_harness.scorers.runner —
``kwargs.setdefault("mode", ...)``). The presence/absence of ``workdir`` is
the source of truth for run vs replay below.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema
from ab_datasets.schemas import ScorerKind, ScorerVerdict, Task

from ab_harness.scorers._base import replay_unsupported, score_to_verdict
from ab_harness.scorers.assertions import load_events, run_assertion_chain

_EXECUTION_MODES: frozenset[str] = frozenset({"run", "replay"})

# Comparison-mode aliases. All map to the same dispatch.
_SCHEMA_MODES: frozenset[str] = frozenset({"schema", "exact_json", "jsonschema"})
_VALUE_EQUALS_MODES: frozenset[str] = frozenset({"json_value_equals", "value_equals", "deep_equal"})
_MARKDOWN_APPEND_MODES: frozenset[str] = frozenset({"append_only_last_entry", "append_only_last_n_entries"})


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


def _load_final_assistant_message(
    trajectory_path: Path,
) -> tuple[Any, str | None]:
    """Pull the final assistant turn's ``model_output`` as JSON.

    Walks the trajectory forward, keeps the last non-empty ``model_output``
    from any ``event=turn role=assistant`` line. Strips common
    code-fence / wrapper noise (``` ```json ... ``` ```) before parsing —
    models often emit JSON inside a fence even with explicit instructions
    to skip them.
    """
    last_msg: str | None = None
    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") != "turn":
                continue
            if ev.get("role") != "assistant":
                continue
            out = ev.get("model_output")
            if isinstance(out, str) and out.strip():
                last_msg = out

    if last_msg is None:
        return None, "no assistant model_output found in trajectory"

    text = last_msg.strip()
    # Strip ```json ... ``` or ``` ... ``` fences when present.
    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            # Drop leading ```[lang] line.
            lines = lines[1:]
            # Drop trailing ``` line, if present.
            if lines and lines[-1].strip().startswith("```"):
                lines = lines[:-1]
            text = "\n".join(lines).strip()

    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"final assistant message is not valid JSON: {exc}"


def _resolve_input(
    *,
    input_source: str,
    target: str | None,
    workdir: Path | None,
    trajectory_path: Path | None,
) -> tuple[Any, str | None]:
    """Dispatch to the correct loader based on ``input``."""
    if input_source == "final_assistant_message":
        if trajectory_path is None:
            return None, "input=final_assistant_message needs a trajectory_path"
        return _load_final_assistant_message(trajectory_path)

    # Default: input is a file path in workdir or reconstructable from trajectory.
    if target is None:
        return None, "`target` is required when input=file"

    if workdir is None:
        if trajectory_path is None:
            return None, "trajectory_path required for replay"
        return _load_target_from_trajectory(trajectory_path, target)
    return _load_target_from_workdir(workdir, target)


def _check_value_equals(
    instance: Any,
    expected: Any,
    *,
    additional_properties_forbidden: bool,
) -> tuple[bool, dict[str, Any]]:
    """Deep-equality check with optional strict-key enforcement.

    When ``additional_properties_forbidden`` is True (the typical
    benchmark intent) and both sides are dicts, the instance's key-set
    must equal the expected key-set exactly. Otherwise, ``==`` semantics:
    Python compares dicts/lists/scalars structurally.
    """
    if additional_properties_forbidden and isinstance(expected, dict) and isinstance(instance, dict):
        extra = sorted(set(instance.keys()) - set(expected.keys()))
        missing = sorted(set(expected.keys()) - set(instance.keys()))
        if extra or missing:
            return False, {
                "error": "key-set mismatch",
                "extra_keys": extra,
                "missing_keys": missing,
            }

    if instance == expected:
        return True, {"equal": True}

    # Best-effort field-level diff when both sides are dicts. Keeps the
    # verdict actionable without dragging in a heavy diff library.
    if isinstance(expected, dict) and isinstance(instance, dict):
        mismatches = []
        for k in sorted(set(expected.keys()) | set(instance.keys())):
            if instance.get(k) != expected.get(k):
                mismatches.append(
                    {"key": k, "expected": expected.get(k), "got": instance.get(k)}
                )
                if len(mismatches) >= 5:
                    break
        return False, {"error": "value mismatch", "mismatches": mismatches}
    return False, {"error": "value mismatch", "expected": expected, "got": instance}


_ENTRY_RE = re.compile(r"(?m)^### .*(?:\n(?!### ).*)*")


def _markdown_entries(text: str) -> list[str]:
    return [m.group(0).rstrip() for m in _ENTRY_RE.finditer(text)]


def _resolve_existing_path(root: Path, rel: str) -> Path | None:
    direct = root / rel
    if direct.exists():
        return direct
    basename = Path(rel).name
    matches = sorted(root.rglob(basename))
    return matches[0] if matches else None


def _markdown_field(entry: str, field: str) -> str | None:
    match = re.search(rf"(?m)^\*\*{re.escape(field)}\*\*:\s*(.*)$", entry)
    return match.group(1).strip() if match else None


def _captured_pytest_failure_text(trajectory_path: Path | None) -> str | None:
    if trajectory_path is None:
        return None
    with trajectory_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            if ev.get("event") != "turn":
                continue
            for ret in ev.get("tool_returns") or []:
                if not isinstance(ret, dict):
                    continue
                exit_code = ret.get("exit_code")
                if not isinstance(exit_code, int) or exit_code == 0:
                    continue
                text = "\n".join(
                    str(ret.get(k) or "")
                    for k in ("stdout", "stderr", "output", "content")
                    if ret.get(k) is not None
                ).strip()
                if text:
                    return text
    return None


def _check_markdown_append_schema(
    *,
    scorer_name: str,
    workdir: Path | None,
    trajectory_path: Path | None,
    target_file: str | None,
    mode: str,
    n: int | None,
    heading_pattern: str | None,
    required_fields: list[str] | None,
    field_patterns: dict[str, str] | None,
    verbatim_required_in_field: dict[str, str] | None,
) -> ScorerVerdict:
    name = scorer_name
    kind = ScorerKind.schema
    if workdir is None:
        return replay_unsupported(name, kind, "workdir required for markdown append schema checks")
    if not target_file:
        return score_to_verdict(name, kind, False, 0.0, {"error": "target_file is required"})
    path = _resolve_existing_path(workdir, target_file)
    if path is None or not path.is_file():
        return score_to_verdict(name, kind, False, 0.0, {"error": f"target_file not found: {target_file}"})
    entries = _markdown_entries(path.read_text(encoding="utf-8"))
    count = int(n or 1) if mode == "append_only_last_n_entries" else 1
    selected = entries[-count:] if count else []
    errors: list[dict[str, Any]] = []
    if len(selected) != count:
        errors.append({"error": "not enough entries", "expected": count, "actual": len(selected)})
    for idx, entry in enumerate(selected):
        heading = entry.splitlines()[0] if entry.splitlines() else ""
        if heading_pattern and not re.search(heading_pattern, heading):
            errors.append({"entry": idx, "field": "<heading>", "error": "heading pattern mismatch", "heading": heading})
        for field in required_fields or []:
            if _markdown_field(entry, field) is None:
                errors.append({"entry": idx, "field": field, "error": "missing required field"})
        for field, pattern in (field_patterns or {}).items():
            value = _markdown_field(entry, field)
            if value is None or not re.search(pattern, value):
                errors.append({"entry": idx, "field": field, "error": "pattern mismatch", "pattern": pattern, "value": value})
        for field, marker in (verbatim_required_in_field or {}).items():
            value = _markdown_field(entry, field) or ""
            required = _captured_pytest_failure_text(trajectory_path) if marker == "captured_pytest_failure_text" else marker
            if required and required not in value:
                errors.append({"entry": idx, "field": field, "error": "required verbatim text missing"})
    return score_to_verdict(
        name,
        kind,
        not errors,
        1.0 if not errors else 0.0,
        {"checked_entries": len(selected), "errors": errors[:10], "total_errors": len(errors)},
    )


def schema_scorer(
    workdir: Path | None = None,
    task: Task | None = None,
    trajectory_path: Path | None = None,
    *,
    mode: str = "run",
    target: str | None = None,
    target_file: str | None = None,
    schema: dict[str, Any] | None = None,
    schema_path: str | Path | None = None,
    expected: Any = None,
    input: str = "file",
    additional_properties_forbidden: bool = False,
    assertions: list[dict[str, Any]] | None = None,
    n: int | None = None,
    heading_pattern: str | None = None,
    required_fields: list[str] | None = None,
    field_patterns: dict[str, str] | None = None,
    verbatim_required_in_field: dict[str, str] | None = None,
    scorer_name: str | None = None,
    **_: Any,
) -> ScorerVerdict:
    name = scorer_name or "schema"
    kind = ScorerKind.schema

    # The runner now uses ``kwargs.setdefault("mode", ...)``, so when YAML
    # sets ``mode: json_value_equals`` we see that value here. When YAML
    # doesn't set ``mode``, the harness fills it with "run" or "replay".
    is_execution_mode = mode in _EXECUTION_MODES

    if is_execution_mode and workdir is None and trajectory_path is None:
        return replay_unsupported(name, kind, "trajectory_path required for replay")

    if mode in _MARKDOWN_APPEND_MODES:
        return _check_markdown_append_schema(
            scorer_name=name,
            workdir=workdir,
            trajectory_path=trajectory_path,
            target_file=target_file,
            mode=mode,
            n=n,
            heading_pattern=heading_pattern,
            required_fields=required_fields,
            field_patterns=field_patterns,
            verbatim_required_in_field=verbatim_required_in_field,
        )

    instance, err = _resolve_input(
        input_source=input,
        target=target,
        workdir=workdir,
        trajectory_path=trajectory_path,
    )
    if err:
        return score_to_verdict(name, kind, False, 0.0, {"error": err})

    # Dispatch to comparison mode. When the YAML didn't specify a
    # comparison mode (so ``mode`` is "run"/"replay"), default to schema
    # validation — the legacy behavior shipped with M1.3.
    comparison_mode = mode if not is_execution_mode else "schema"

    def _with_assertions(base: ScorerVerdict) -> ScorerVerdict:
        if not assertions or not base.pass_:
            return base
        if trajectory_path is None:
            return score_to_verdict(
                name,
                kind,
                False,
                0.0,
                {"schema": base.detail, "assertions_error": "trajectory_path required for schema assertions"},
            )
        assertion_verdict = run_assertion_chain(
            name,
            load_events(trajectory_path),
            workdir,
            None,
            assertions,
        )
        ok = bool(assertion_verdict.pass_)
        return score_to_verdict(
            name,
            kind,
            ok,
            assertion_verdict.score if ok else min(base.score, assertion_verdict.score),
            {"schema": base.detail, "assertions": assertion_verdict.detail},
        )

    if comparison_mode in _SCHEMA_MODES:
        loaded = _load_schema(schema, schema_path, workdir)
        if isinstance(loaded, str):
            return score_to_verdict(name, kind, False, 0.0, {"error": loaded})

        validator = jsonschema.Draft202012Validator(loaded)
        errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
        if not errors:
            return _with_assertions(score_to_verdict(name, kind, True, 1.0, {"errors": []}))
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

    if comparison_mode in _VALUE_EQUALS_MODES:
        if expected is None:
            return score_to_verdict(
                name,
                kind,
                False,
                0.0,
                {"error": "mode=json_value_equals requires `expected`"},
            )
        ok, detail = _check_value_equals(
            instance,
            expected,
            additional_properties_forbidden=bool(additional_properties_forbidden),
        )
        return _with_assertions(score_to_verdict(name, kind, ok, 1.0 if ok else 0.0, detail))

    return score_to_verdict(
        name,
        kind,
        False,
        0.0,
        {"error": f"unknown schema mode: {comparison_mode!r}"},
    )
