from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from .task import TrustTier
from .tier import Tier
from .trajectory import ScorerVerdict


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
