"""L0 taxonomy invariants. Locks the suite coverage in place so the
inventory in `docs/L0-inventory.md` stays accurate as tasks are added.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest
import yaml
from ab_datasets.schemas import Task

DATASETS_ROOT = Path(__file__).resolve().parent.parent / "ab_datasets"
L0_DIR = DATASETS_ROOT / "L0_foundation"

L0_FILES: tuple[Path, ...] = tuple(sorted(L0_DIR.glob("*.yaml")))


def _load(path: Path) -> Task:
    return Task.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def l0_tasks() -> list[Task]:
    return [_load(p) for p in L0_FILES]


# Suites we expect L0 to cover, with floor counts.
EXPECTED_SUITES: dict[str, int] = {
    "file-ops": 5,                       # L0_001, 002, 006, 007, 009, 010
    "schema-fill": 1,                    # L0_003
    "exec": 1,                           # L0_004
    "extract": 1,                        # L0_005
    "long-context-niah": 3,              # L0_101..103
    "long-context-multi-hop": 1,         # L0_201
    "long-context-aggregation": 1,       # L0_202
    "tool-use": 5,                       # L0_301..308 (8 actual; ≥5 floor)
    "instruction-following": 3,          # L0_401..403
    "faithfulness": 3,                   # L0_501..505 (5 actual; ≥3 floor)
    "environment-probe": 6,              # L0_601..608 (8 actual; ≥6 floor)
}


def test_suite_coverage_meets_floor(l0_tasks: list[Task]) -> None:
    counts = Counter(t.suite for t in l0_tasks)
    for suite, floor in EXPECTED_SUITES.items():
        actual = counts.get(suite, 0)
        assert actual >= floor, (
            f"L0 suite {suite!r} has only {actual} task(s), floor is {floor}; "
            f"available counts: {dict(counts)}"
        )


def test_environment_probe_mirror_pair_exists(l0_tasks: list[Task]) -> None:
    """L0_605 and L0_606 are a mirror pair: same prompt, opposite required behaviour
    at different tiers. Both must exist or the tier-delta proof breaks."""
    ids = {t.id for t in l0_tasks}
    assert "L0_605" in ids, "L0_605 (T0 no-fake-skill) missing — mirror with L0_606 breaks"
    assert "L0_606" in ids, "L0_606 (T2 dispatches skill) missing — mirror with L0_605 breaks"
    pair = {t.id: t for t in l0_tasks if t.id in {"L0_605", "L0_606"}}
    assert pair["L0_605"].config.required_tier == "T0", "L0_605 must be required_tier=T0"
    assert pair["L0_606"].config.required_tier == "T2", "L0_606 must be required_tier=T2"


def test_tier_delta_canary_present(l0_tasks: list[Task]) -> None:
    """L0_608 is the factual-canary across all tiers."""
    canary = next((t for t in l0_tasks if t.id == "L0_608"), None)
    assert canary is not None, "L0_608 tier-delta canary missing"
    declared = {canary.config.required_tier, *canary.config.also_run_on}
    assert {"T0", "T1", "T2", "T3"}.issubset(declared), (
        f"L0_608 must cover all four tiers; got {declared}"
    )


def test_environment_probes_have_tier_diversity(l0_tasks: list[Task]) -> None:
    """The environment-probe suite must collectively probe at least three tiers."""
    probes = [t for t in l0_tasks if t.suite == "environment-probe"]
    tiers_seen: set[str] = set()
    for t in probes:
        tiers_seen.add(t.config.required_tier)
        tiers_seen.update(t.config.also_run_on)
    assert len(tiers_seen & {"T0", "T1", "T2", "T3"}) >= 3, (
        f"environment-probe suite covers only tiers {tiers_seen}; expected ≥3"
    )


def test_no_orphan_suite(l0_tasks: list[Task]) -> None:
    """Every L0 suite name must appear in the expected inventory.
    Catches typos in `suite:` field that would silently fragment taxonomy."""
    actual_suites = {t.suite for t in l0_tasks}
    expected = set(EXPECTED_SUITES.keys())
    orphan = actual_suites - expected
    assert not orphan, (
        f"unexpected L0 suite(s): {orphan}; update EXPECTED_SUITES in "
        f"test_l0_taxonomy.py and docs/L0-inventory.md if intentional"
    )


def test_l0_minimum_size(l0_tasks: list[Task]) -> None:
    """Build spec §2: P0 target = 20, P1 stretch = 30. Lock current floor at 36."""
    assert len(l0_tasks) >= 36, (
        f"L0 has only {len(l0_tasks)} tasks; floor is 36 (above P1 stretch target)"
    )
