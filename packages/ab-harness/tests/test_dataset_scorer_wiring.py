"""Dataset-wide scorer wiring guards.

These tests catch authoring mistakes that schema validation cannot see:
unknown scorer names, unknown assertion kinds, and assertion-chain configs
that would otherwise become decorative YAML.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from ab_harness.scorers import KIND_DEFAULT_REGISTRY, SCORER_REGISTRY
from ab_harness.scorers.assertions import _ASSERTION_KINDS

DATASETS_ROOT = Path(__file__).resolve().parents[3] / "packages" / "ab-datasets" / "ab_datasets"


def _task_yaml_files() -> list[Path]:
    return sorted(DATASETS_ROOT.rglob("*.yaml"))


def test_all_dataset_scorers_resolve() -> None:
    problems: list[tuple[str, str, str, str]] = []
    for path in _task_yaml_files():
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        for spec in data.get("scorer_chain") or []:
            kind = spec.get("kind")
            name = spec.get("name")
            if kind not in KIND_DEFAULT_REGISTRY and name not in SCORER_REGISTRY:
                problems.append((data.get("id", path.stem), "missing_scorer", str(kind), str(name)))
    assert not problems


def test_all_dataset_assertion_kinds_are_registered() -> None:
    problems: list[tuple[str, str, str]] = []
    for path in _task_yaml_files():
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        for spec in data.get("scorer_chain") or []:
            for assertion in (spec.get("config") or {}).get("assertions") or []:
                kind = assertion.get("kind")
                if kind not in _ASSERTION_KINDS:
                    problems.append((data.get("id", path.stem), spec.get("name"), str(kind)))
    assert not problems


def test_assertion_chain_configs_have_real_assertions_or_shorthand() -> None:
    shorthand_keys = {
        "expected",
        "must_exist",
        "must_be_absent",
        "forbid_bom",
        "forbid_crlf",
        "preserve_crlf",
        "require_utf8",
        "forbidden",
        "forbidden_substrings",
    }
    problems: list[tuple[str, str]] = []
    for path in _task_yaml_files():
        data: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8"))
        for spec in data.get("scorer_chain") or []:
            if spec.get("kind") != "deterministic":
                continue
            name = spec.get("name")
            if name in SCORER_REGISTRY and name not in {"file_diff", "exec", "tool_skill", "context_efficiency", "latency_cost"}:
                cfg = spec.get("config") or {}
                if not cfg.get("assertions") and not any(key in cfg for key in shorthand_keys):
                    problems.append((data.get("id", path.stem), str(name)))
    assert not problems
