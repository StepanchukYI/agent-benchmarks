"""Repo-wide task invariants — runs against every shipped task YAML.

Was originally written for a 5-layer Phase-0 pilot. Now generalized to
every `ab_datasets/L*/**/*.yaml` task file present in the repo.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from pathlib import Path

import pytest
import yaml
from ab_datasets.schemas import Layer, ScorerKind, Task, TrustTier

DATASETS_ROOT = Path(__file__).resolve().parent.parent / "ab_datasets"


def _all_task_files() -> list[Path]:
    files: list[Path] = []
    for layer_dir in DATASETS_ROOT.iterdir():
        if not layer_dir.is_dir() or not layer_dir.name.startswith("L"):
            continue
        files.extend(sorted(layer_dir.rglob("*.yaml")))
    return files


TASK_FILES: tuple[Path, ...] = tuple(_all_task_files())


LAYER_MAX_TRUST: dict[Layer, set[TrustTier]] = {
    Layer.L0: {TrustTier.official, TrustTier.verified, TrustTier.self_reported},
    Layer.L1: {TrustTier.verified, TrustTier.self_reported},
    Layer.L2: {TrustTier.verified, TrustTier.self_reported},
    Layer.L3: {TrustTier.verified, TrustTier.self_reported},
    Layer.L4: {TrustTier.verified, TrustTier.self_reported},
    Layer.L5: {TrustTier.self_reported},
}

_DETERMINISTIC_LIKE: frozenset[ScorerKind] = frozenset(
    {
        ScorerKind.deterministic,
        ScorerKind.schema,
        ScorerKind.exec,
        ScorerKind.state_diff,
        ScorerKind.privacy_check,
    }
)


def _load(path: Path) -> Task:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Task.model_validate(data)


def _ids(files: Iterable[Path]) -> list[str]:
    return [p.name for p in files]


def test_at_least_one_task_present() -> None:
    assert TASK_FILES, "no task YAMLs found under ab_datasets/L*/"


@pytest.mark.parametrize("path", TASK_FILES, ids=_ids(TASK_FILES))
def test_task_yaml_validates_against_schema(path: Path) -> None:
    task = _load(path)
    head, _, tail = task.id.partition("_")
    assert head in {"L0", "L1", "L2", "L3", "L3a", "L4", "L5"}, task.id
    assert tail.isdigit() and len(tail) == 3, task.id


@pytest.mark.parametrize("path", TASK_FILES, ids=_ids(TASK_FILES))
def test_task_weights_sum_to_one(path: Path) -> None:
    task = _load(path)
    total = sum(task.weights.values())
    assert math.isclose(total, 1.0, abs_tol=1e-9), (
        f"{task.id} weights sum to {total}, expected 1.0; weights={task.weights}"
    )


@pytest.mark.parametrize("path", TASK_FILES, ids=_ids(TASK_FILES))
def test_task_has_deterministic_scorer(path: Path) -> None:
    task = _load(path)
    kinds = {s.kind for s in task.scorer_chain}
    assert kinds & _DETERMINISTIC_LIKE, (
        f"{task.id} has no deterministic scorer; chain kinds={[k.value for k in kinds]}"
    )


@pytest.mark.parametrize("path", TASK_FILES, ids=_ids(TASK_FILES))
def test_task_has_privacy_check(path: Path) -> None:
    task = _load(path)
    has_privacy = any(s.kind is ScorerKind.privacy_check for s in task.scorer_chain)
    assert has_privacy, f"{task.id} is missing a privacy_check scorer in its chain"


@pytest.mark.parametrize("path", TASK_FILES, ids=_ids(TASK_FILES))
def test_task_trust_tier_within_layer_ceiling(path: Path) -> None:
    task = _load(path)
    allowed = LAYER_MAX_TRUST[task.layer]
    assert task.trust_tier_ceiling in allowed, (
        f"{task.id} layer={task.layer.value} declares "
        f"trust_tier_ceiling={task.trust_tier_ceiling.value}, "
        f"but layer permits only {[t.value for t in allowed]}"
    )


@pytest.mark.parametrize("path", TASK_FILES, ids=_ids(TASK_FILES))
def test_task_acceptance_criteria_nonempty(path: Path) -> None:
    task = _load(path)
    assert len(task.acceptance_criteria) >= 1, f"{task.id} has no acceptance criteria"


@pytest.mark.parametrize("path", TASK_FILES, ids=_ids(TASK_FILES))
def test_task_required_tier_is_canonical(path: Path) -> None:
    task = _load(path)
    canonical = {"T0", "T1", "T2", "T3"}
    assert task.config.required_tier in canonical, task.config.required_tier
    assert task.config.recommended_tier in canonical, task.config.recommended_tier
    for tier in task.config.also_run_on:
        assert tier in canonical, f"{task.id} also_run_on contains non-canonical {tier!r}"


def test_l0_tasks_have_no_llm_judge() -> None:
    """LSN-007: L0 = re-runnable from trajectory alone; no LLM-judge in chain."""
    l0_files = [p for p in TASK_FILES if p.parent.name == "L0_foundation"]
    for path in l0_files:
        task = _load(path)
        kinds = [s.kind for s in task.scorer_chain]
        assert ScorerKind.llm_judge not in kinds, (
            f"{task.id} has llm_judge in chain; L0 must be fully deterministic"
        )
