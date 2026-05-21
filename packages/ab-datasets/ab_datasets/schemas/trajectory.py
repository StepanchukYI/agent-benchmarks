from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .task import ScorerKind
from .tier import Tier


class RunStatus(StrEnum):
    completed = "completed"
    timeout = "timeout"
    unrunnable = "unrunnable"
    error = "error"


class Turn(BaseModel):
    # Disable Pydantic's `model_` protected namespace so `model_output` is allowed.
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    idx: int = Field(ge=0)
    role: Literal["user", "assistant", "tool"]
    prompt_delta: str | None = None
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    tool_returns: list[dict[str, Any]] = Field(default_factory=list)
    model_output: str = ""
    vault_state_diff: dict[str, Any] | None = None
    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)


class ScorerVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    scorer_name: str
    kind: ScorerKind
    # `pass` is a reserved word in Python — accept "pass" on the wire via alias.
    pass_: bool = Field(alias="pass")
    score: float
    detail: str | dict[str, Any] = ""


class Totals(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tokens_in: int = Field(default=0, ge=0)
    tokens_out: int = Field(default=0, ge=0)
    latency_ms: int = Field(default=0, ge=0)
    cost_usd: float = Field(default=0.0, ge=0.0)
    score: float = 0.0


class Trajectory(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    run_id: str
    task_id: str
    model: str
    harness: str
    tier: Tier
    tier_hash: str | None = None
    dataset_version: str
    prompt_template_hash: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus | None = None
    turns: list[Turn] = Field(default_factory=list)
    scorer_verdicts: list[ScorerVerdict] = Field(default_factory=list)
    totals: Totals | None = None
