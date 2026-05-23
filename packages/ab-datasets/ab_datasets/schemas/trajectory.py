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


class SamplingConfig(BaseModel):
    """Sampling-knob values the model was called with.

    Recorded in trajectory `run_start` so the leaderboard can normalise
    cross-runner comparisons against the recommended defaults
    (temperature=0, top_p=1.0, max_output_tokens >= 4096, stream=False).
    See `docs/result-sensitivity-axes.md` axes #2, #3, #10.
    """

    model_config = ConfigDict(extra="forbid")

    temperature: float | None = None
    top_p: float | None = None
    top_k: int | None = None
    max_output_tokens: int | None = None
    stream: bool | None = None


class ReasoningConfig(BaseModel):
    """Reasoning / thinking budget the model was instructed to use.

    See `docs/result-sensitivity-axes.md` axis #1 — same model with
    `thinking=off` vs `thinking=high` differs 20-40% on reasoning-
    sensitive tasks. Both fields optional; runners that don't expose
    reasoning controls leave both None.
    """

    model_config = ConfigDict(extra="forbid")

    effort: Literal["off", "low", "medium", "high", "xhigh", "auto"] | None = None
    budget_tokens: int | None = None


class IsolationInfo(BaseModel):
    """Record of how the runner isolated the operator's HOME from the benchmark agent.

    Emitted on run_start so the leaderboard can show isolation provenance
    alongside scores. Other runners emit isolation=None until they adopt
    clean-HOME isolation.
    """

    model_config = ConfigDict(extra="forbid")

    mode: str
    """Isolation strategy used. ``"clean_home"`` = fresh temp HOME, real
    ~/.claude is physically invisible. Other modes possible in future."""

    home: str
    """Absolute path to the ephemeral HOME the subprocess saw."""

    real_home_untouched: bool
    """True when the runner never wrote to the operator's real HOME."""

    bare: bool
    """True when the claude CLI was launched with ``--bare`` (no keychain auth)."""


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
    # Operator-supplied human-readable name for the custom CLAUDE.md prompt
    # (via `ab run --prompt-label`). The leaderboard shows this instead of the
    # raw tier_hash. None for the 4 built-in tier presets / no custom prompt.
    prompt_label: str | None = None
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus | None = None
    turns: list[Turn] = Field(default_factory=list)
    scorer_verdicts: list[ScorerVerdict] = Field(default_factory=list)
    totals: Totals | None = None
    # ── Sensitivity-axis fields (additive, all optional) ─────────────
    # See docs/result-sensitivity-axes.md. Build spec §12: never remove
    # fields. New fields default to None so old trajectories validate.
    sampling: SamplingConfig | None = None
    reasoning: ReasoningConfig | None = None
    # The verbatim system prompt the model received. Captures both the
    # harness-injected default ("You are a helpful assistant") AND the
    # tier-injected operator CLAUDE.md. Source of truth for axis #11.
    system_prompt_verbatim: str | None = None
    # Model's context window in tokens. Filled from MODEL_REGISTRY at
    # runner construction; lets the leaderboard mark window-exhausted
    # runs as `n/a` rather than failure. Axis #7.
    model_context_window_tokens: int | None = None
    # Output truncation signals. Axis #3.
    output_truncated: bool | None = None
    output_tokens_used: int | None = None
    # Per-task max-turn budget (declared by task YAML scorer or by the
    # runner's hard cap). Axis #12.
    turn_cap: int | None = None
    # Subprocess isolation record — how the runner isolated the operator's
    # environment from the benchmark agent. Emitted by runners that support
    # clean-HOME isolation; None for runners that don't record isolation yet.
    isolation: IsolationInfo | None = None
