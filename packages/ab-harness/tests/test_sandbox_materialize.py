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


def test_materialize_claude_md_override_content_addresses(tmp_path):
    """A custom --claude-md becomes workdir/CLAUDE.md and changes tier_hash.

    Two different override files at the same tier must yield two distinct
    tier_hashes — that is what makes a custom prompt a distinct leaderboard
    row. The verbatim text is exposed on the result for the run_start reveal.
    """
    task = SimpleNamespace(id="L0_001")
    karpathy = tmp_path / "karpathy.md"
    karpathy.write_text("# Karpathy rules\nBe terse.\n", encoding="utf-8")
    other = tmp_path / "other.md"
    other.write_text("# Different rules\nBe verbose.\n", encoding="utf-8")

    res_k = materialize(_FIXTURES, Tier.T0, task, tmp_path / "k", claude_md_override=karpathy)
    res_o = materialize(_FIXTURES, Tier.T0, task, tmp_path / "o", claude_md_override=other)
    res_k2 = materialize(_FIXTURES, Tier.T0, task, tmp_path / "k2", claude_md_override=karpathy)

    # Same content → same hash; different content → different hash.
    assert res_k.tier_hash == res_k2.tier_hash
    assert res_k.tier_hash != res_o.tier_hash

    # The override is materialized as the project CLAUDE.md the agent reads.
    assert (tmp_path / "k" / "CLAUDE.md").read_text() == "# Karpathy rules\nBe terse.\n"
    assert res_k.claude_md_text == "# Karpathy rules\nBe terse.\n"

    # And it differs from the same tier with no override.
    res_vanilla = materialize(_FIXTURES, Tier.T0, task, tmp_path / "v")
    assert res_vanilla.tier_hash != res_k.tier_hash
    assert res_vanilla.claude_md_text is None
