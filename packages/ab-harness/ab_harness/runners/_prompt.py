"""Prompt assembly for runners — composes task description + acceptance criteria."""

from __future__ import annotations

from typing import Any


def build_prompt(task: Any) -> str:
    description = (getattr(task, "description", "") or "").rstrip()
    criteria = list(getattr(task, "acceptance_criteria", []) or [])

    parts: list[str] = []
    if description:
        parts.append(description)

    if criteria:
        parts.append("")
        parts.append("Acceptance criteria:")
        for i, line in enumerate(criteria, start=1):
            parts.append(f"{i}. {line}")

    return "\n".join(parts).strip() + ("\n" if parts else "")
