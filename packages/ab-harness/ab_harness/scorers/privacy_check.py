"""Privacy-check scorer (LSN-006). Scans trajectory content against pattern list."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

_DEFAULT_PATTERNS: list[str] = []


def _load_patterns(patterns_path: str | Path | None) -> list[re.Pattern[str]]:
    if patterns_path is None:
        return [re.compile(p) for p in _DEFAULT_PATTERNS]
    p = Path(patterns_path)
    if not p.exists():
        return [re.compile(pat) for pat in _DEFAULT_PATTERNS]
    try:
        import yaml
    except ImportError:
        return [re.compile(pat) for pat in _DEFAULT_PATTERNS]
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    raw = data.get("patterns", []) if isinstance(data, dict) else []
    return [re.compile(str(pat)) for pat in raw]


def privacy_check_scorer(
    content: str = "",
    patterns_path: str | Path | None = None,
    **_: Any,
) -> Any:
    from ab_datasets.schemas import ScorerKind, ScorerVerdict  # type: ignore[attr-defined]

    patterns = _load_patterns(patterns_path)
    hits = [pat.pattern for pat in patterns if pat.search(content)]
    return ScorerVerdict(
        scorer_name="privacy_check",
        kind=ScorerKind.privacy_check,
        pass_=not hits,
        score=1.0 if not hits else 0.0,
        detail=f"matches={hits}" if hits else "no privacy pattern matches",
    )
