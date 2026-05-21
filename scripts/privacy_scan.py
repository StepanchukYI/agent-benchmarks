"""Scan the working tree for privacy-pattern matches.

Exits 0 if there are zero high-severity matches, 1 otherwise.
Medium and low matches are reported on stderr but do not fail the run.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PATTERNS_FILE = REPO_ROOT / "docs" / "privacy-patterns.yaml"

EXCLUDED_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
    ".next",
    ".turbo",
    ".gitnexus",
}

EXCLUDED_SUFFIXES = {".lock", ".lockb", ".min.js", ".map"}

MAX_FILE_BYTES = 1_000_000


def load_patterns() -> list[dict]:
    if not PATTERNS_FILE.exists():
        print(f"privacy_scan: patterns file not found: {PATTERNS_FILE}", file=sys.stderr)
        return []
    with PATTERNS_FILE.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    raw = data.get("patterns", [])
    out: list[dict] = []
    for entry in raw:
        try:
            out.append(
                {
                    "id": entry["id"],
                    "description": entry["description"],
                    "regex": re.compile(entry["regex"]),
                    "severity": entry.get("severity", "high"),
                    "exclude_paths": tuple(entry.get("exclude_paths", []) or []),
                }
            )
        except (KeyError, re.error) as exc:
            print(f"privacy_scan: bad pattern entry {entry!r}: {exc}", file=sys.stderr)
    return out


def iter_files(root: Path):
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & EXCLUDED_DIRS:
            continue
        if path.suffix in EXCLUDED_SUFFIXES:
            continue
        if path.name.endswith(".lock"):
            continue
        try:
            if path.stat().st_size > MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        yield path


def scan_file(path: Path, rel: Path, patterns: list[dict]) -> list[tuple[int, dict, str]]:
    matches: list[tuple[int, dict, str]] = []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return matches
    rel_str = str(rel)
    for lineno, line in enumerate(text.splitlines(), start=1):
        for pat in patterns:
            if any(ex in rel_str for ex in pat["exclude_paths"]):
                continue
            if pat["regex"].search(line):
                matches.append((lineno, pat, line.rstrip()))
    return matches


def main() -> int:
    patterns = load_patterns()
    if not patterns:
        print("privacy_scan: no patterns loaded; aborting", file=sys.stderr)
        return 1

    high_count = 0
    medium_count = 0
    low_count = 0

    for path in iter_files(REPO_ROOT):
        rel = path.relative_to(REPO_ROOT)
        if rel == Path("docs/privacy-patterns.yaml"):
            continue
        if rel == Path("scripts/privacy_scan.py"):
            continue
        for lineno, pat, _line in scan_file(path, rel, patterns):
            severity = pat["severity"]
            print(
                f"{rel}:{lineno}: [{pat['id']}] ({severity}) {pat['description']}",
                file=sys.stderr,
            )
            if severity == "high":
                high_count += 1
            elif severity == "medium":
                medium_count += 1
            else:
                low_count += 1

    print(
        f"privacy_scan: high={high_count} medium={medium_count} low={low_count}",
        file=sys.stderr,
    )
    return 0 if high_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
