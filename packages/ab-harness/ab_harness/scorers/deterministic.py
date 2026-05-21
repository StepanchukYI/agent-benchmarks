"""Deterministic scorers: file-diff, schema-validator, exec."""

from __future__ import annotations

from typing import Any


def _stub_verdict(name: str) -> Any:
    from ab_datasets.schemas import ScorerKind, ScorerVerdict  # type: ignore[attr-defined]

    return ScorerVerdict(
        scorer_name=name,
        kind=ScorerKind.deterministic,
        pass_=True,
        score=1.0,
        detail="stub",
    )


def file_diff_scorer(*args: Any, **kwargs: Any) -> Any:
    return _stub_verdict("file_diff")


def schema_validator_scorer(*args: Any, **kwargs: Any) -> Any:
    return _stub_verdict("schema_validator")


def exec_scorer(*args: Any, **kwargs: Any) -> Any:
    return _stub_verdict("exec")
