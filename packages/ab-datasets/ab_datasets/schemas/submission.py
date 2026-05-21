from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .task import TrustTier
from .tier import Tier
from .trajectory import ReasoningConfig, SamplingConfig, ScorerVerdict


class AgentConfig(BaseModel):
    """Cross-submission knob snapshot for sensitivity-aware filtering.

    Mirrors the per-run values in `Trajectory.sampling` /
    `Trajectory.reasoning`. Submission carries them too so the
    leaderboard can filter without re-opening the trajectory.

    See `docs/result-sensitivity-axes.md` for the full inventory of
    axes (12 secondary axes; this captures the structural ones).
    """

    model_config = ConfigDict(extra="forbid")

    sampling: SamplingConfig | None = None
    reasoning: ReasoningConfig | None = None
    model_context_window_tokens: int | None = None
    system_prompt_sha256: str | None = None
    turn_cap: int | None = None


class Submission(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    id: str
    source_repo: str
    source_commit_sha: str
    registered_repo_id: str
    trajectory_path: str
    scorer_verdicts: list[ScorerVerdict] = Field(default_factory=list)
    trust_tier: TrustTier
    submitted_at: datetime
    model: str
    tier: Tier
    dataset_version: str
    # Sensitivity-axis snapshot. Additive, optional — old submissions
    # validate unchanged. Build spec §12 (never remove fields).
    agent_config: AgentConfig | None = None
