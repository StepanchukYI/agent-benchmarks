"""materialize() copies tier files into a fresh workdir and records tier_hash."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from ab_datasets.schemas import Tier
from ab_harness.sandbox import MaterializedTier, materialize

_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_FIXTURES = (
    Path(__file__).resolve().parents[2]
    / "ab-datasets"
    / "fixtures"
    / "config_tiers"
)


def test_materialize_t0_vanilla(tmp_path):
    task = SimpleNamespace(id="L0_001")
    result = materialize(_FIXTURES, Tier.T0, task, tmp_path)
    assert isinstance(result, MaterializedTier)
    assert result.tier is Tier.T0
    assert _HEX64.match(result.tier_hash), result.tier_hash
    assert not (tmp_path / "CLAUDE.md").exists()
    assert (tmp_path / ".claude" / "SKILLS.txt").read_text() == ""
    assert (tmp_path / ".claude" / "MCPS.txt").read_text() == ""


def test_materialize_t2_personal(tmp_path):
    task = SimpleNamespace(id="L1_001")
    workdir_a = tmp_path / "a"
    workdir_b = tmp_path / "b"
    result_a = materialize(_FIXTURES, Tier.T2, task, workdir_a)
    result_b = materialize(_FIXTURES, Tier.T2, task, workdir_b)

    assert _HEX64.match(result_a.tier_hash)
    assert result_a.tier_hash == result_b.tier_hash

    assert (workdir_a / "CLAUDE.md").exists()
    skills = (workdir_a / ".claude" / "SKILLS.txt").read_text().splitlines()
    assert skills == ["memory:memory-session", "memory:memory-write"]
    mcps = (workdir_a / ".claude" / "MCPS.txt").read_text().splitlines()
    assert mcps == ["obsidian-memory"]
    assert (workdir_a / "vault" / "T2_seed_small" / "hub.md").exists()
