"""materialize() returns a 64-hex SHA-256 string."""

from __future__ import annotations

import re
from types import SimpleNamespace

from ab_harness.sandbox.docker import materialize

_HEX64 = re.compile(r"^[0-9a-f]{64}$")


def test_materialize_returns_sha256_hex(tmp_path):
    tier = SimpleNamespace(tier="T0", total_sha256=None)
    task = SimpleNamespace(id="L0_001")
    result = materialize(tier, task, tmp_path)
    assert _HEX64.match(result), result


def test_materialize_prefers_total_sha256(tmp_path):
    tier_a = SimpleNamespace(tier="T0", total_sha256="abc")
    tier_b = SimpleNamespace(tier="T3", total_sha256="abc")
    task = SimpleNamespace(id="anything")
    assert materialize(tier_a, task, tmp_path) == materialize(tier_b, task, tmp_path)
