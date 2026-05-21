from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("ab_datasets.schemas")

from ab_datasets.schemas import Difficulty, Layer, Task, TaskConfig
from ab_harness.scorers.schema import schema_scorer


def _task() -> Task:
    return Task(
        id="L0_003",
        layer=Layer.L0,
        suite="schema",
        title="t",
        description="d",
        config=TaskConfig(required_tier="T0", recommended_tier="T0"),
        difficulty=Difficulty.easy,
    )


_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "age": {"type": "integer", "minimum": 0},
    },
    "required": ["name", "age"],
    "additionalProperties": False,
}


def test_schema_valid(tmp_path: Path) -> None:
    (tmp_path / "person.json").write_text(json.dumps({"name": "alice", "age": 30}), encoding="utf-8")
    verdict = schema_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        target="person.json",
        schema=_SCHEMA,
    )
    assert verdict.pass_ is True
    assert verdict.score == 1.0


def test_schema_invalid_missing_field(tmp_path: Path) -> None:
    (tmp_path / "person.json").write_text(json.dumps({"name": "alice"}), encoding="utf-8")
    verdict = schema_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        target="person.json",
        schema=_SCHEMA,
    )
    assert verdict.pass_ is False
    assert isinstance(verdict.detail, dict)
    assert verdict.detail["errors"]


def test_schema_invalid_type(tmp_path: Path) -> None:
    (tmp_path / "person.json").write_text(
        json.dumps({"name": "alice", "age": "thirty"}), encoding="utf-8"
    )
    verdict = schema_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        target="person.json",
        schema=_SCHEMA,
    )
    assert verdict.pass_ is False


def test_schema_from_path(tmp_path: Path) -> None:
    (tmp_path / "person.json").write_text(json.dumps({"name": "a", "age": 1}), encoding="utf-8")
    (tmp_path / "person.schema.json").write_text(json.dumps(_SCHEMA), encoding="utf-8")
    verdict = schema_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        target="person.json",
        schema_path="person.schema.json",
    )
    assert verdict.pass_ is True


def test_schema_target_missing(tmp_path: Path) -> None:
    verdict = schema_scorer(
        workdir=tmp_path,
        task=_task(),
        mode="run",
        target="missing.json",
        schema=_SCHEMA,
    )
    assert verdict.pass_ is False
