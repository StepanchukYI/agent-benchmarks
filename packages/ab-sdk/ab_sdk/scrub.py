"""Privacy auto-scrub — apply scrub replacements to trajectories + run-dir files.

Complements ``publish_gate.check_publish_ready`` (which DETECTS) by providing
a FIX path. The gate flags issues; this module rewrites the offending file
in place using each pattern's ``scrub_replacement`` field.

A pattern WITHOUT ``scrub_replacement`` (or with ``null``) is detect-only —
the gate will still flag it but the scrubber leaves it alone. Tokens are a
good candidate for detect-only since a token replaced with ``[REDACTED]``
no longer authenticates; the operator must rotate the secret AND remove it
from history, not just edit the file.

Top-level helpers:

* :func:`scrub_text(text, patterns) -> tuple[str, list[ScrubHit]]`
  Pure transform. Returns the rewritten text and one hit per replacement.

* :func:`scrub_file(path, patterns, *, dry_run=False) -> list[ScrubHit]`
  Reads the file as utf-8, applies ``scrub_text``, writes back if not dry_run
  AND hits > 0. Returns the hit list.

* :func:`scrub_run_dir(run_dir, patterns, *, dry_run=False) -> dict`
  Walks the run dir (trajectory.jsonl + scores.json + metadata.yaml +
  workdir/**) and scrubs each text-ish file. Returns
  ``{files_scanned, files_modified, hits_total, by_pattern}``.

* :func:`load_scrub_patterns(yaml_path) -> list[ScrubPattern]`
  Reads the standard privacy-patterns.yaml and compiles only entries with
  a ``scrub_replacement`` field.

The replacement is plain text (not a regex backreference template). Use
literal strings like ``"~"`` or ``"[REDACTED]"``. Backref support would
let pattern authors echo back the matched secret, which we don't want.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from .results import TRAJECTORY_FILE

_log = logging.getLogger(__name__)

# Skip binary-ish files entirely. Same set as scripts/privacy_scan.py.
_TEXT_EXCLUDE_SUFFIXES = frozenset(
    {".pyc", ".pyo", ".so", ".dylib", ".png", ".jpg", ".jpeg", ".gif", ".webp",
     ".pdf", ".zip", ".gz", ".tar", ".whl", ".woff", ".woff2", ".ttf", ".otf",
     ".lock", ".lockb", ".min.js", ".map"}
)

# Hard cap per-file scrub size. Trajectories can grow large but no single
# turn should be >1MB of text; refuse the file if it's clearly not text.
_MAX_FILE_BYTES = 25 * 1024 * 1024


@dataclass(frozen=True)
class ScrubPattern:
    """One scrub rule compiled from privacy-patterns.yaml."""

    id: str
    description: str
    regex: re.Pattern[str]
    replacement: str
    severity: str


@dataclass(frozen=True)
class ScrubHit:
    """One concrete replacement event in a single file or text blob."""

    pattern_id: str
    matched: str
    replaced_with: str
    span: tuple[int, int]


def load_scrub_patterns(patterns_yaml: Path) -> list[ScrubPattern]:
    """Read privacy-patterns.yaml and return only entries with scrub_replacement.

    Patterns without ``scrub_replacement`` (the common case for tokens —
    redacting them in place is not a fix, just camouflage) are skipped.
    """
    raw = yaml.safe_load(patterns_yaml.read_text(encoding="utf-8")) or {}
    items = raw.get("patterns", []) if isinstance(raw, dict) else []
    out: list[ScrubPattern] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        replacement = entry.get("scrub_replacement")
        if replacement is None:
            continue
        regex_src = entry.get("regex")
        if not regex_src:
            continue
        try:
            compiled = re.compile(str(regex_src))
        except re.error as exc:
            _log.warning("bad regex for pattern %r: %s", entry.get("id"), exc)
            continue
        out.append(
            ScrubPattern(
                id=str(entry.get("id", "<unnamed>")),
                description=str(entry.get("description", "")),
                regex=compiled,
                replacement=str(replacement),
                severity=str(entry.get("severity", "medium")),
            )
        )
    return out


def scrub_text(
    text: str,
    patterns: list[ScrubPattern],
) -> tuple[str, list[ScrubHit]]:
    """Apply every pattern in order. Returns (rewritten_text, hits)."""
    hits: list[ScrubHit] = []
    current = text
    for pat in patterns:
        def _on_match(m: re.Match[str], _pat: ScrubPattern = pat) -> str:
            hits.append(
                ScrubHit(
                    pattern_id=_pat.id,
                    matched=m.group(0),
                    replaced_with=_pat.replacement,
                    span=m.span(),
                )
            )
            return _pat.replacement

        current = pat.regex.sub(_on_match, current)
    return current, hits


def scrub_file(
    path: Path,
    patterns: list[ScrubPattern],
    *,
    dry_run: bool = False,
) -> list[ScrubHit]:
    """Scrub ``path`` in place. No-op (and returns []) for non-text files.

    Returns the list of replacements made. Empty list = file untouched.
    When ``dry_run`` is True the file is never written; hits are still
    computed and returned so callers can preview.
    """
    if path.suffix in _TEXT_EXCLUDE_SUFFIXES:
        return []
    try:
        size = path.stat().st_size
    except OSError:
        return []
    if size > _MAX_FILE_BYTES:
        _log.warning("scrub_file: %s exceeds %d bytes, skipped", path, _MAX_FILE_BYTES)
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return []

    rewritten, hits = scrub_text(text, patterns)
    if hits and not dry_run and rewritten != text:
        path.write_text(rewritten, encoding="utf-8")
    return hits


def _walk_text_files(root: Path):
    excluded_dirs = {
        ".git", "node_modules", ".venv", "venv", "__pycache__",
        ".mypy_cache", ".ruff_cache", ".pytest_cache", "dist", "build",
    }
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & excluded_dirs:
            continue
        if path.suffix in _TEXT_EXCLUDE_SUFFIXES:
            continue
        yield path


def scrub_run_dir(
    run_dir: Path,
    patterns: list[ScrubPattern],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scrub every text file in ``run_dir`` (trajectory + scores + workdir/**).

    Returns a summary dict::

        {
            "run_dir": str(run_dir),
            "dry_run": dry_run,
            "files_scanned": int,
            "files_modified": int,
            "hits_total": int,
            "by_pattern": {pattern_id: int},
            "per_file": [{path: str, hits: int, patterns: [id, ...]}, ...],
        }
    """
    files_scanned = 0
    files_modified = 0
    hits_total = 0
    by_pattern: dict[str, int] = {}
    per_file: list[dict[str, Any]] = []

    for path in _walk_text_files(run_dir):
        files_scanned += 1
        hits = scrub_file(path, patterns, dry_run=dry_run)
        if not hits:
            continue
        files_modified += 1
        hits_total += len(hits)
        ids: list[str] = []
        for hit in hits:
            by_pattern[hit.pattern_id] = by_pattern.get(hit.pattern_id, 0) + 1
            if hit.pattern_id not in ids:
                ids.append(hit.pattern_id)
        per_file.append(
            {
                "path": str(path.relative_to(run_dir)),
                "hits": len(hits),
                "patterns": ids,
            }
        )

    return {
        "run_dir": str(run_dir),
        "dry_run": dry_run,
        "files_scanned": files_scanned,
        "files_modified": files_modified,
        "hits_total": hits_total,
        "by_pattern": by_pattern,
        "per_file": per_file,
    }


def scrub_trajectory(
    trajectory_path: Path,
    patterns: list[ScrubPattern],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Scrub a trajectory.jsonl file line by line, preserving event boundaries.

    Each line is a JSON object; we deserialize-rewrite-reserialize so the
    file remains valid JSONL even if a replacement would have changed the
    text length. Lines that fail to parse are passed through verbatim with
    a logged warning.
    """
    if not trajectory_path.exists():
        return {"hits_total": 0, "lines": 0, "by_pattern": {}}

    out_lines: list[str] = []
    hits_total = 0
    by_pattern: dict[str, int] = {}
    line_count = 0

    with trajectory_path.open("r", encoding="utf-8") as fh:
        for raw in fh:
            line_count += 1
            stripped = raw.rstrip("\n")
            if not stripped.strip():
                out_lines.append(raw)
                continue
            try:
                event = json.loads(stripped)
            except json.JSONDecodeError:
                _log.warning(
                    "scrub_trajectory: bad JSON at line %d, passed through",
                    line_count,
                )
                out_lines.append(raw)
                continue

            serialized = json.dumps(event, sort_keys=False, ensure_ascii=False)
            rewritten, hits = scrub_text(serialized, patterns)
            if hits:
                hits_total += len(hits)
                for hit in hits:
                    by_pattern[hit.pattern_id] = (
                        by_pattern.get(hit.pattern_id, 0) + 1
                    )
            out_lines.append(rewritten + "\n")

    if hits_total > 0 and not dry_run:
        trajectory_path.write_text("".join(out_lines), encoding="utf-8")

    return {
        "trajectory_path": str(trajectory_path),
        "dry_run": dry_run,
        "lines": line_count,
        "hits_total": hits_total,
        "by_pattern": by_pattern,
    }


def scrub_run_dir_complete(
    run_dir: Path,
    patterns: list[ScrubPattern],
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    """Convenience: scrub trajectory + run-dir files, return combined summary.

    The trajectory pass uses ``scrub_trajectory`` (line-by-line, JSON-aware);
    the rest of the run dir uses ``scrub_run_dir`` (plain text).
    """
    run_dir = Path(run_dir)
    trajectory_path = run_dir / TRAJECTORY_FILE

    traj_result: dict[str, Any] = {"hits_total": 0, "lines": 0, "by_pattern": {}}
    if trajectory_path.exists():
        traj_result = scrub_trajectory(trajectory_path, patterns, dry_run=dry_run)

    # Skip the trajectory in the generic pass so we don't double-process it.
    other_result = scrub_run_dir(
        run_dir,
        patterns,
        dry_run=dry_run,
    )
    if str(trajectory_path.relative_to(run_dir)) in {
        item["path"] for item in other_result["per_file"]
    }:
        # In dry-run + already-scrubbed, the generic pass may also pick it
        # up. Filter so the report doesn't double-count.
        other_result["per_file"] = [
            item for item in other_result["per_file"]
            if item["path"] != str(trajectory_path.relative_to(run_dir))
        ]
        other_result["files_modified"] = len(other_result["per_file"])

    combined_by_pattern: dict[str, int] = dict(traj_result.get("by_pattern", {}))
    for k, v in other_result.get("by_pattern", {}).items():
        combined_by_pattern[k] = combined_by_pattern.get(k, 0) + v

    return {
        "run_dir": str(run_dir),
        "dry_run": dry_run,
        "trajectory": traj_result,
        "other_files": other_result,
        "hits_total": traj_result.get("hits_total", 0) + other_result["hits_total"],
        "by_pattern": combined_by_pattern,
    }


__all__ = [
    "ScrubHit",
    "ScrubPattern",
    "load_scrub_patterns",
    "scrub_file",
    "scrub_run_dir",
    "scrub_run_dir_complete",
    "scrub_text",
    "scrub_trajectory",
]
