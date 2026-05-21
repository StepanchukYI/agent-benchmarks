"""Tier manifest loading, verification, and rollup-hash computation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from ab_datasets.schemas import TierManifest


def load_manifest(path: Path) -> TierManifest:
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    return TierManifest.model_validate(data)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _resolve(root: Path, ref: str) -> Path:
    # vault snapshots live under fixtures/, manifests under fixtures/config_tiers/<tier>/;
    # let absolute paths fall through and resolve relative paths against both roots.
    p = Path(ref)
    if p.is_absolute():
        return p
    candidate = root / ref
    if candidate.exists():
        return candidate
    # Snapshots are referenced from the fixtures root (one level up from config_tiers/<tier>).
    parent_fixtures = root.parent.parent
    return parent_fixtures / ref


def verify_hashes(manifest: TierManifest, root: Path) -> list[str]:
    errors: list[str] = []
    if manifest.claude_md:
        path = _resolve(root, manifest.claude_md["path"])
        expected = manifest.claude_md.get("sha256")
        if expected:
            actual = _sha256_file(path)
            if actual != expected:
                errors.append(f"claude_md sha256 mismatch at {path}: {actual} != {expected}")
    if manifest.claude_local_md:
        path = _resolve(root, manifest.claude_local_md["path"])
        expected = manifest.claude_local_md.get("sha256")
        if expected:
            actual = _sha256_file(path)
            if actual != expected:
                errors.append(f"claude_local_md sha256 mismatch at {path}: {actual} != {expected}")
    if manifest.vault_state:
        snap = manifest.vault_state.get("snapshot")
        expected = manifest.vault_state.get("sha256")
        if snap and expected:
            path = _resolve(root, snap)
            actual = _sha256_file(path)
            if actual != expected:
                errors.append(f"vault_state sha256 mismatch at {path}: {actual} != {expected}")
    return errors


def compute_total_sha256(manifest: TierManifest, root: Path) -> str:
    h = hashlib.sha256()
    h.update(manifest.tier.value.encode("utf-8"))
    h.update(b"\n")

    if manifest.claude_md:
        path = _resolve(root, manifest.claude_md["path"])
        h.update(b"claude_md:")
        h.update(_sha256_file(path).encode("utf-8"))
        h.update(b"\n")

    if manifest.claude_local_md:
        path = _resolve(root, manifest.claude_local_md["path"])
        h.update(b"claude_local_md:")
        h.update(_sha256_file(path).encode("utf-8"))
        h.update(b"\n")

    for sid in sorted(s["id"] for s in manifest.skills):
        h.update(b"skill:")
        h.update(sid.encode("utf-8"))
        h.update(b"\n")

    for mid in sorted(m["id"] for m in manifest.mcps):
        h.update(b"mcp:")
        h.update(mid.encode("utf-8"))
        h.update(b"\n")

    if manifest.vault_state and manifest.vault_state.get("snapshot"):
        path = _resolve(root, manifest.vault_state["snapshot"])
        h.update(b"vault_state:")
        h.update(_sha256_file(path).encode("utf-8"))
        h.update(b"\n")

    return h.hexdigest()
