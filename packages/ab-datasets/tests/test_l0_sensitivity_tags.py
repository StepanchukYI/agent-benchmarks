"""Lock sensitivity-tag taxonomy on L0 tasks.

`docs/result-sensitivity-axes.md` enumerates the secondary axes that
move scores in ways not captured by (model x runner x tier x task).
For each axis we ship a tag; this test asserts the tags are applied
to the tasks where the axis materially bites.

If a tag is added/removed intentionally, update the lookup tables
below AND `docs/result-sensitivity-axes.md` together.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ab_datasets.schemas import Task

DATASETS_ROOT = Path(__file__).resolve().parent.parent / "ab_datasets"
L0_DIR = DATASETS_ROOT / "L0_foundation"


def _load(path: Path) -> Task:
    return Task.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def l0_by_id() -> dict[str, Task]:
    return {Task.model_validate(yaml.safe_load(p.read_text())).id: _load(p)
            for p in sorted(L0_DIR.glob("*.yaml"))}


# Task ids that MUST carry each sensitivity tag (additions allowed,
# removals require updating both this list and the axes doc).
EXPECT_REASONING_SENSITIVE: frozenset[str] = frozenset({
    "L0_101", "L0_102", "L0_103",        # NIAH (esp. adversarial)
    "L0_201", "L0_202",                  # multi-hop, aggregation
    "L0_303", "L0_304", "L0_305",
    "L0_306", "L0_307", "L0_308",        # tool-use judgement / mapping
    "L0_401", "L0_402",                  # nested IF, exact count
    "L0_501", "L0_503",                  # abstain, contradiction
    "L0_602", "L0_604", "L0_605",
    "L0_607",                            # rule application
})

EXPECT_BYTE_EXACT: frozenset[str] = frozenset({
    "L0_001", "L0_002", "L0_006", "L0_007", "L0_010",
    "L0_101", "L0_102", "L0_103", "L0_201", "L0_202",
    "L0_401", "L0_402", "L0_403",
    "L0_502", "L0_505",
    "L0_608",
})

EXPECT_OUTPUT_NORM: frozenset[str] = EXPECT_BYTE_EXACT  # always co-occur

EXPECT_CONTEXT_WINDOW_SENSITIVE: frozenset[str] = frozenset({
    "L0_101", "L0_102", "L0_103",
    "L0_201", "L0_202",
})

EXPECT_FACTUAL_RECALL: frozenset[str] = frozenset({
    "L0_603",  # Eiffel Tower year
    "L0_608",  # gold = Au
})

EXPECT_RUNNER_SKILL_DISPATCH: frozenset[str] = frozenset({
    "L0_605", "L0_606",
})

EXPECT_LANGUAGE_RUSSIAN: frozenset[str] = frozenset({
    "L0_605", "L0_606",
})

EXPECT_TOKENIZER_SENSITIVE: frozenset[str] = frozenset({
    "L0_402",
})


def _check(l0_by_id: dict[str, Task], tag: str, expected: frozenset[str]) -> None:
    missing = []
    extras = []
    for tid, task in l0_by_id.items():
        has = tag in task.tags
        should = tid in expected
        if should and not has:
            missing.append(tid)
        if has and not should:
            extras.append(tid)
    msg_parts = []
    if missing:
        msg_parts.append(f"tasks missing {tag!r}: {sorted(missing)}")
    if extras:
        msg_parts.append(f"unexpected {tag!r} on: {sorted(extras)}")
    assert not msg_parts, "; ".join(msg_parts)


def test_reasoning_sensitive_tag(l0_by_id: dict[str, Task]) -> None:
    _check(l0_by_id, "reasoning-sensitive", EXPECT_REASONING_SENSITIVE)


def test_byte_exact_output_tag(l0_by_id: dict[str, Task]) -> None:
    _check(l0_by_id, "byte-exact-output", EXPECT_BYTE_EXACT)


def test_output_normalization_sensitive_tag(l0_by_id: dict[str, Task]) -> None:
    _check(l0_by_id, "output-normalization-sensitive", EXPECT_OUTPUT_NORM)


def test_context_window_sensitive_tag(l0_by_id: dict[str, Task]) -> None:
    _check(l0_by_id, "context-window-sensitive", EXPECT_CONTEXT_WINDOW_SENSITIVE)


def test_factual_recall_tag(l0_by_id: dict[str, Task]) -> None:
    _check(l0_by_id, "factual-recall", EXPECT_FACTUAL_RECALL)


def test_runner_skill_dispatch_tag(l0_by_id: dict[str, Task]) -> None:
    _check(l0_by_id, "runner-skill-dispatch", EXPECT_RUNNER_SKILL_DISPATCH)


def test_language_russian_tag(l0_by_id: dict[str, Task]) -> None:
    _check(l0_by_id, "language-russian", EXPECT_LANGUAGE_RUSSIAN)


def test_tokenizer_sensitive_tag(l0_by_id: dict[str, Task]) -> None:
    _check(l0_by_id, "tokenizer-sensitive", EXPECT_TOKENIZER_SENSITIVE)


def test_every_l0_task_has_at_least_one_sensitivity_tag_or_is_simple(
    l0_by_id: dict[str, Task],
) -> None:
    """Tasks that carry NO sensitivity tag should be on a small allow-list
    of genuinely simple capability checks. This catches accidental gaps
    where a non-trivial task was added without classifying its axes."""
    SENSITIVITY_TAGS = {
        "reasoning-sensitive", "byte-exact-output",
        "output-normalization-sensitive", "context-window-sensitive",
        "factual-recall", "runner-skill-dispatch", "language-russian",
        "tokenizer-sensitive",
    }
    SIMPLE_ALLOW = {"L0_003", "L0_004", "L0_005", "L0_008", "L0_009",
                    "L0_301", "L0_302", "L0_504", "L0_601"}
    for tid, task in l0_by_id.items():
        has_any = bool(set(task.tags) & SENSITIVITY_TAGS)
        if not has_any:
            assert tid in SIMPLE_ALLOW, (
                f"{tid} carries no sensitivity tag and is not on the simple "
                f"allow-list; either tag it or add it to SIMPLE_ALLOW with rationale"
            )
