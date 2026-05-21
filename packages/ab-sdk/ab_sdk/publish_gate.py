"""Publish gate — validation + high-severity privacy scan before `ab publish`."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

from .results import TRAJECTORY_FILE, validate

_PATTERNS_FILENAME = "docs/privacy-patterns.yaml"
_ENV_OVERRIDE = "AB_PRIVACY_PATTERNS"


def _discover_patterns_file(start: Path) -> Path | None:
    env_path = os.environ.get(_ENV_OVERRIDE)
    if env_path:
        candidate = Path(env_path)
        if candidate.exists():
            return candidate
    for parent in [start, *start.parents]:
        candidate = parent / _PATTERNS_FILENAME
        if candidate.exists():
            return candidate
    return None


def _load_high_severity_patterns(patterns_path: Path) -> list[dict[str, Any]]:
    raw = yaml.safe_load(patterns_path.read_text(encoding="utf-8")) or {}
    items = raw.get("patterns", []) if isinstance(raw, dict) else []
    compiled: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("severity") != "high":
            continue
        regex = item.get("regex")
        if not regex:
            continue
        try:
            pattern = re.compile(str(regex))
        except re.error:
            continue
        compiled.append(
            {
                "id": item.get("id", "<unnamed>"),
                "pattern": pattern,
                "description": item.get("description", ""),
            }
        )
    return compiled


def check_publish_ready(
    run_dir: Path,
    *,
    patterns_path: Path | None = None,
) -> tuple[bool, list[str]]:
    """Return (ok, issues). Called by `ab publish` (M2.7) before push."""
    run_dir = Path(run_dir)
    issues = validate(run_dir, require_privacy_pass=True)

    resolved = patterns_path if patterns_path else _discover_patterns_file(run_dir)
    if resolved is None:
        issues.append(
            "privacy scan: could not locate docs/privacy-patterns.yaml "
            "(set AB_PRIVACY_PATTERNS or place under repo root)"
        )
        return (False, issues)

    patterns = _load_high_severity_patterns(resolved)
    trajectory = run_dir / TRAJECTORY_FILE
    if trajectory.exists():
        with trajectory.open("r", encoding="utf-8") as fh:
            for lineno, raw in enumerate(fh, start=1):
                line = raw.rstrip("\n")
                if not line.strip():
                    continue
                for pat in patterns:
                    if pat["pattern"].search(line):
                        issues.append(
                            f"privacy scan: pattern {pat['id']!r} matched "
                            f"trajectory.jsonl line {lineno}"
                        )

    return (not issues, issues)


__all__ = ["check_publish_ready"]
