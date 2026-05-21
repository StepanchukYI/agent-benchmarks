#!/usr/bin/env python3
"""Regenerate `packages/ab-datasets/fixtures/manifest.yaml` from disk.

The manifest declares every fixture (repo seed, vault snapshot, tier
config) the benchmark dataset ships, with sha256 + size + visibility.
The CI privacy gate + Track B's resolve test both rely on it.

Usage:

    python scripts/build_fixtures_manifest.py [--check] [--out PATH]

Flags:
    --check   diff-mode: exit 1 if the regenerated manifest differs from
              the on-disk version. Use in CI to detect drift.
    --out     write to a different path (default: the live manifest).

What's catalogued:

* ``fixtures/repos/<suite>/<task_id>/`` — every per-task fixture tree.
  sha256 = sha256 of (relpath, content_sha256) pairs sorted lexically
  (order-independent). size = sum of file bytes.
* ``fixtures/vault_snapshots/*.tar.gz`` — vault tarballs as opaque
  files (sha256 of the tar bytes, size = tar size).
* ``fixtures/config_tiers/<tier>/manifest.yaml`` — tier descriptors.

Skips:
* `__pycache__/`, `.gitkeep`, `conftest.py`, the manifest itself.
* The `mcp_mocks/` directory (descriptors, not bench inputs).
"""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent
_FIXTURES = _REPO_ROOT / "packages" / "ab-datasets" / "fixtures"
_MANIFEST = _FIXTURES / "manifest.yaml"

_SKIP_NAMES = {"__pycache__", "manifest.yaml", "conftest.py"}
_SKIP_EXTS = {".pyc"}


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _tree_sha256_and_size(root: Path) -> tuple[str, int]:
    """Hash a directory tree: sha256 over (relpath, file_sha256) pairs.

    Order-independent. Empty dirs hash to e3b0… (sha256 of empty input).
    """
    digests: list[tuple[str, str]] = []
    total_bytes = 0
    if not root.exists():
        return hashlib.sha256(b"").hexdigest(), 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in _SKIP_NAMES:
            continue
        if path.suffix in _SKIP_EXTS:
            continue
        if "__pycache__" in path.parts:
            continue
        rel = str(path.relative_to(root))
        digests.append((rel, _file_sha256(path)))
        total_bytes += path.stat().st_size
    combined = hashlib.sha256()
    for rel, h in sorted(digests):
        combined.update(rel.encode("utf-8"))
        combined.update(b"\x00")
        combined.update(h.encode("ascii"))
        combined.update(b"\x00")
    return combined.hexdigest(), total_bytes


def _collect_repo_fixtures() -> list[dict]:
    out: list[dict] = []
    repos_root = _FIXTURES / "repos"
    if not repos_root.exists():
        return out
    for suite_dir in sorted(repos_root.iterdir()):
        if not suite_dir.is_dir() or suite_dir.name.startswith("."):
            continue
        for task_dir in sorted(suite_dir.iterdir()):
            if not task_dir.is_dir() or task_dir.name.startswith("."):
                continue
            sha, size = _tree_sha256_and_size(task_dir)
            rel = task_dir.relative_to(_FIXTURES).as_posix() + "/"
            out.append(
                {
                    "id": f"{suite_dir.name}_{task_dir.name}",
                    "kind": "repo",
                    "path": f"fixtures/{rel}",
                    "sha256": sha,
                    "size": size,
                    "description": f"{suite_dir.name} seed fixture for task {task_dir.name}.",
                    "visibility": "public",
                }
            )
    return out


def _collect_vault_snapshots() -> list[dict]:
    out: list[dict] = []
    root = _FIXTURES / "vault_snapshots"
    if not root.exists():
        return out
    for path in sorted(root.iterdir()):
        if path.name.startswith(".") or path.is_dir():
            continue
        if path.suffix not in {".gz", ".tgz", ".zst"}:
            continue
        sha = _file_sha256(path)
        out.append(
            {
                "id": f"vault_{path.stem.replace('.tar', '')}",
                "kind": "vault_snapshot",
                "path": f"fixtures/vault_snapshots/{path.name}",
                "sha256": sha,
                "size": path.stat().st_size,
                "description": f"Anonymized vault snapshot {path.name}.",
                "visibility": "public",
            }
        )
    return out


def _collect_tier_manifests() -> list[dict]:
    out: list[dict] = []
    root = _FIXTURES / "config_tiers"
    if not root.exists():
        return out
    for tier_dir in sorted(root.iterdir()):
        if not tier_dir.is_dir():
            continue
        manifest = tier_dir / "manifest.yaml"
        if not manifest.exists():
            continue
        sha = _file_sha256(manifest)
        out.append(
            {
                "id": f"tier_{tier_dir.name}",
                "kind": "tier_manifest",
                "path": f"fixtures/config_tiers/{tier_dir.name}/manifest.yaml",
                "sha256": sha,
                "size": manifest.stat().st_size,
                "description": f"Tier manifest for {tier_dir.name}.",
                "visibility": "public",
            }
        )
    return out


def build_manifest() -> dict:
    fixtures: list[dict] = []
    fixtures.extend(_collect_repo_fixtures())
    fixtures.extend(_collect_vault_snapshots())
    fixtures.extend(_collect_tier_manifests())
    fixtures.sort(key=lambda entry: entry["id"])
    return {"fixtures": fixtures}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if the regenerated manifest differs from the on-disk version.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_MANIFEST,
        help=f"Output path (default: {_MANIFEST}).",
    )
    args = parser.parse_args()

    manifest = build_manifest()
    rendered = yaml.safe_dump(manifest, sort_keys=False, default_flow_style=False)

    if args.check:
        existing = args.out.read_text(encoding="utf-8") if args.out.exists() else ""
        if existing != rendered:
            print(
                f"fixtures manifest drift detected at {args.out}; "
                f"run `python scripts/build_fixtures_manifest.py` to regenerate.",
                file=sys.stderr,
            )
            return 1
        return 0

    args.out.write_text(rendered, encoding="utf-8")
    n = len(manifest["fixtures"])
    print(f"wrote {n} entries to {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
