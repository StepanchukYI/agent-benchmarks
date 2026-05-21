"""load_manifest -> verify_hashes -> compute_total_sha256 round-trip."""

from __future__ import annotations

import re
from pathlib import Path

from ab_datasets.schemas import Tier
from ab_harness.sandbox import compute_total_sha256, load_manifest, verify_hashes

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "ab-datasets"
    / "fixtures"
    / "config_tiers"
)


def _dir_for(tier: Tier, slug: str) -> Path:
    return _FIXTURES / f"{tier.value}_{slug}"


def test_t0_manifest_roundtrip():
    root = _dir_for(Tier.T0, "vanilla")
    manifest = load_manifest(root / "manifest.yaml")
    assert manifest.tier is Tier.T0
    assert verify_hashes(manifest, root) == []
    total = compute_total_sha256(manifest, root)
    assert _HEX64.match(total)
    assert compute_total_sha256(manifest, root) == total


def test_t1_manifest_roundtrip():
    root = _dir_for(Tier.T1, "minimal")
    manifest = load_manifest(root / "manifest.yaml")
    assert manifest.tier is Tier.T1
    assert manifest.claude_md is not None
    assert verify_hashes(manifest, root) == []
    total = compute_total_sha256(manifest, root)
    assert _HEX64.match(total)


def test_t2_manifest_roundtrip():
    root = _dir_for(Tier.T2, "personal")
    manifest = load_manifest(root / "manifest.yaml")
    assert manifest.tier is Tier.T2
    assert len(manifest.skills) == 2
    assert len(manifest.mcps) == 1
    assert manifest.vault_state is not None
    assert verify_hashes(manifest, root) == []
    total_a = compute_total_sha256(manifest, root)
    total_b = compute_total_sha256(manifest, root)
    assert total_a == total_b
    assert _HEX64.match(total_a)


def test_t3_manifest_roundtrip():
    root = _dir_for(Tier.T3, "full")
    manifest = load_manifest(root / "manifest.yaml")
    assert manifest.tier is Tier.T3
    assert manifest.claude_md is None
    assert verify_hashes(manifest, root) == []
