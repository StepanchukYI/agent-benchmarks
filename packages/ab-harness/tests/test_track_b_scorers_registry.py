"""Track B scorer name discovery + registry coverage.

Walks every L0 task YAML, collects the set of `- name:` entries from
scorer chains, and asserts each one is wired into `SCORER_REGISTRY` and
`SCORER_PILLAR_MAP`. This is the safety net that turns "track B added a new
scorer name" into a deterministic test failure instead of a runtime crash.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ab_harness.scorers import SCORER_PILLAR_MAP, SCORER_REGISTRY, pillar_for

DATASETS_ROOT = (
    Path(__file__).resolve().parents[3] / "packages" / "ab-datasets" / "ab_datasets"
)
L0_DIR = DATASETS_ROOT / "L0_foundation"

PILLARS_ALLOWED: set[str] = {
    "correctness",
    "tool_skill",
    "context_efficiency",
    "latency_cost",
    "memory_specific",
}


def _scorer_names_in_yaml(path: Path) -> list[str]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    chain = data.get("scorer_chain") or []
    return [s["name"] for s in chain if isinstance(s, dict) and "name" in s]


def _l0_task_files() -> list[Path]:
    if not L0_DIR.is_dir():
        return []
    return sorted(L0_DIR.glob("*.yaml"))


def _all_scorer_names() -> set[str]:
    seen: set[str] = set()
    for p in _l0_task_files():
        seen.update(_scorer_names_in_yaml(p))
    return seen


@pytest.mark.skipif(not L0_DIR.is_dir(), reason="L0 dataset not present")
def test_l0_yamls_exist() -> None:
    assert _l0_task_files(), "no L0 task YAMLs found"


@pytest.mark.skipif(not L0_DIR.is_dir(), reason="L0 dataset not present")
def test_every_track_b_scorer_is_registered() -> None:
    names = _all_scorer_names()
    missing = sorted(n for n in names if n not in SCORER_REGISTRY)
    assert not missing, (
        f"L0 YAMLs reference {len(missing)} scorer names not in SCORER_REGISTRY: {missing}"
    )


@pytest.mark.skipif(not L0_DIR.is_dir(), reason="L0 dataset not present")
def test_every_track_b_scorer_has_pillar_mapping() -> None:
    names = _all_scorer_names()
    # `pillar_for` defaults unknowns to `correctness`, but Track B's authoritative
    # scorers should have explicit entries so weights compute predictably.
    missing = sorted(n for n in names if n not in SCORER_PILLAR_MAP)
    assert not missing, (
        f"L0 YAMLs reference {len(missing)} scorer names not in SCORER_PILLAR_MAP: {missing}"
    )


@pytest.mark.skipif(not L0_DIR.is_dir(), reason="L0 dataset not present")
def test_track_b_pillars_are_canonical() -> None:
    names = _all_scorer_names()
    bad = [(n, pillar_for(n)) for n in names if pillar_for(n) not in PILLARS_ALLOWED]
    assert not bad, f"non-canonical pillars: {bad}"


def test_registry_callables_have_minimal_signature() -> None:
    """Every Track B scorer must accept the harness's standard kwargs."""
    import inspect

    from ab_harness.scorers.track_b_scorers import TRACK_B_SCORERS

    for name, fn in TRACK_B_SCORERS.items():
        sig = inspect.signature(fn)
        params = sig.parameters
        # Must tolerate workdir / task / trajectory_path positional/keyword args
        # plus **cfg for assertion config blob.
        assert "workdir" in params, name
        assert "task" in params, name
        assert "trajectory_path" in params, name
