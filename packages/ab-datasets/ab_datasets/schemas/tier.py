from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Tier(StrEnum):
    T0 = "T0"
    T1 = "T1"
    T2 = "T2"
    T3 = "T3"


class TierManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tier: Tier
    description: str
    claude_md: dict[str, Any] | None = None
    claude_local_md: dict[str, Any] | None = None
    skills: list[dict[str, Any]] = Field(default_factory=list)
    mcps: list[dict[str, Any]] = Field(default_factory=list)
    vault_state: dict[str, Any] | None = None
    total_sha256: str | None = None
