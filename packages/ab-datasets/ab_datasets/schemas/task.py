from __future__ import annotations

from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field


class Layer(StrEnum):
    L0 = "L0"
    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"
    L5 = "L5"


class Visibility(StrEnum):
    public = "public"
    private = "private"


class TrustTier(StrEnum):
    self_reported = "self_reported"
    verified = "verified"
    official = "official"


class Difficulty(StrEnum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class ScorerKind(StrEnum):
    deterministic = "deterministic"
    llm_judge = "llm_judge"
    state_diff = "state_diff"
    schema = "schema"
    exec = "exec"
    privacy_check = "privacy_check"


class ScorerSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(description="Scorer instance name; matches verdict.scorer_name.")]
    kind: ScorerKind
    config: dict[str, Any] = Field(default_factory=dict)


ScorerChain = list[ScorerSpec]


class TaskConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required_tier: Annotated[str, Field(description="Minimum tier needed to attempt the task, e.g. T0..T3.")]
    recommended_tier: str
    also_run_on: list[str] = Field(default_factory=list)
    requires: dict[str, Any] = Field(default_factory=dict)


class Fixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    kind: Annotated[str, Field(description="Fixture category: vault_snapshot, repo, mcp_mock, config_tier, etc.")]
    sha256: str
    path: str
    size: int = Field(ge=0)
    description: str = ""
    visibility: Visibility = Visibility.public


class Task(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    layer: Layer
    suite: str
    title: str
    description: str
    fixture_ref: str | None = None
    scorer_chain: ScorerChain = Field(default_factory=list)
    config: TaskConfig
    acceptance_criteria: list[str] = Field(default_factory=list)
    weights: dict[str, float] = Field(default_factory=dict)
    difficulty: Difficulty = Difficulty.medium
    tags: list[str] = Field(default_factory=list)
    visibility: Visibility = Visibility.public
    trust_tier_ceiling: TrustTier = TrustTier.verified
