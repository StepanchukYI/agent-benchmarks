#!/usr/bin/env python3
"""Privacy auto-scrub CLI.

Apply pattern-based replacements to a run directory (or a single file).
Detect-only patterns (no scrub_replacement) are skipped — `scripts/privacy_scan.py`
still reports those for manual triage.

Usage:

    # Scrub a full run directory (trajectory.jsonl + scores.json + workdir/**)
    python scripts/privacy_scrub.py /path/to/run-dir

    # Dry-run: report what would change, don't write
    python scripts/privacy_scrub.py /path/to/run-dir --dry-run

    # Scrub a single file in place
    python scripts/privacy_scrub.py /path/to/trajectory.jsonl --file

    # Custom patterns file (default: docs/privacy-patterns.yaml at repo root)
    python scripts/privacy_scrub.py /path/to/run-dir --patterns custom.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Allow running from a checkout without installing ab-sdk.
_repo_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_repo_root / "packages" / "ab-sdk"))

from ab_sdk.scrub import (  # noqa: E402
    load_scrub_patterns,
    scrub_file,
    scrub_run_dir_complete,
)


def _default_patterns_path() -> Path:
    return _repo_root / "docs" / "privacy-patterns.yaml"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("target", type=Path, help="run directory or file to scrub")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report planned changes, don't write",
    )
    parser.add_argument(
        "--file",
        action="store_true",
        help="treat target as a single file (default: scrub the whole run dir)",
    )
    parser.add_argument(
        "--patterns",
        type=Path,
        default=None,
        help="patterns YAML (default: docs/privacy-patterns.yaml at repo root)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="machine-readable JSON output",
    )
    args = parser.parse_args()

    target: Path = args.target
    if not target.exists():
        print(f"target not found: {target}", file=sys.stderr)
        return 2

    patterns_path = args.patterns or _default_patterns_path()
    if not patterns_path.exists():
        print(f"patterns file not found: {patterns_path}", file=sys.stderr)
        return 2

    patterns = load_scrub_patterns(patterns_path)
    if not patterns:
        print(
            f"no scrubbable patterns in {patterns_path} "
            f"(detect-only patterns are not auto-fixable; rotate secrets manually)",
            file=sys.stderr,
        )
        return 0

    if args.file:
        if not target.is_file():
            print(f"--file requires a file path: {target}", file=sys.stderr)
            return 2
        hits = scrub_file(target, patterns, dry_run=args.dry_run)
        result = {
            "mode": "file",
            "path": str(target),
            "dry_run": args.dry_run,
            "hits_total": len(hits),
            "by_pattern": _hits_by_pattern(hits),
        }
    else:
        if not target.is_dir():
            print(f"target must be a directory (or pass --file): {target}", file=sys.stderr)
            return 2
        result = scrub_run_dir_complete(target, patterns, dry_run=args.dry_run)

    if args.json:
        print(json.dumps(result, indent=2, default=str))
    else:
        _human_report(result)
    return 0


def _hits_by_pattern(hits) -> dict[str, int]:
    counts: dict[str, int] = {}
    for hit in hits:
        counts[hit.pattern_id] = counts.get(hit.pattern_id, 0) + 1
    return counts


def _human_report(result: dict) -> None:
    if result.get("mode") == "file":
        verb = "would scrub" if result["dry_run"] else "scrubbed"
        print(f"{verb} {result['path']}: {result['hits_total']} hit(s)")
        for pid, n in (result.get("by_pattern") or {}).items():
            print(f"  - {pid}: {n}")
        return

    print(f"{'DRY-RUN ' if result['dry_run'] else ''}scrubbed {result['run_dir']}")
    traj = result.get("trajectory") or {}
    other = result.get("other_files") or {}
    print(
        f"  trajectory: {traj.get('hits_total', 0)} hit(s) "
        f"across {traj.get('lines', 0)} line(s)"
    )
    print(
        f"  other files: {other.get('files_modified', 0)}/{other.get('files_scanned', 0)} "
        f"modified, {other.get('hits_total', 0)} hit(s)"
    )
    print(f"  total hits: {result['hits_total']}")
    if result.get("by_pattern"):
        print("  by pattern:")
        for pid, n in sorted(result["by_pattern"].items()):
            print(f"    - {pid}: {n}")


if __name__ == "__main__":
    sys.exit(main())
