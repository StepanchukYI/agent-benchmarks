"""Runner factory — pick the right runner given a model id + scaffold hint.

Single entry point so call sites (ab CLI, server-dispatched runs) don't
hardcode "if model startswith claude → ClaudeCodeRunner else ...".

Decision tree (top-down):

1. ``runner="mock"`` → :class:`MockRunner`. Used in tests; no API key.
2. ``runner="claude-code"`` and model is claude → :class:`ClaudeCodeRunner`
   (CLI under OAuth keychain or ANTHROPIC_API_KEY).
3. ``runner="local"`` or model.local=True → :class:`OpenAICompatRunner`
   pointed at the scaffold's local URL (Ollama/LM Studio/vLLM/llama.cpp).
4. ``runner="anthropic-compat"`` → :class:`AnthropicCompatRunner` with
   per-vendor base_url. Used for Anthropic + Chinese Anthropic-compat
   proxies (GLM, Kimi, Qwen, MiniMax, DeepSeek).
5. ``runner="openai-compat"`` → :class:`OpenAICompatRunner`. Catch-all
   for OpenAI + any chat-completions endpoint.
6. Stubs (``opencode``, ``pi-agent``, ``hermes-agent``, ``nanobot``,
   ``cursor``) → :class:`StubRunner` that fails fast with "not yet
   implemented" pointing at the spec.

The factory ALSO looks up the model in the registry to pre-fill compat
defaults (api_compat, local flag, vendor base_url) so callers can pass
``model="glm-4.6"`` and get the right wire shape without thinking.
"""

from __future__ import annotations

from typing import Any

from ab_harness.models import (
    get_model_info,
    local_base_url,
    vendor_base_url,
)
from ab_harness.runners.anthropic_compat import AnthropicCompatRunner
from ab_harness.runners.base import BaseRunner
from ab_harness.runners.claude_code import ClaudeCodeRunner
from ab_harness.runners.codex_cli import CodexCLIRunner
from ab_harness.runners.gemini_cli import GeminiCLIRunner
from ab_harness.runners.mock import MockRunner
from ab_harness.runners.openai_compat import OpenAICompatRunner
from ab_harness.runners.pi_agent import PiAgentRunner


class StubRunner(BaseRunner):
    """Placeholder for runners we haven't implemented yet.

    Returns a clean error from ``run_task`` instead of crashing on import.
    Lets the CLI list it (``ab run --runner codex-cli``) and surface a
    helpful "wire this up first" message at run time.
    """

    def __init__(self, *, scaffold: str, model: str, reason: str = "") -> None:
        self._scaffold = scaffold
        self._model = model
        self._reason = reason or f"{scaffold} runner is a stub; see build spec sec 8."

    def name(self) -> str:
        return f"{self._scaffold}({self._model}) [stub]"

    def version(self) -> str:
        return f"{self._scaffold}-stub@v0"

    def prepare(self, tier_manifest: Any) -> None:
        return None

    def run_task(self, task: Any, trajectory_writer: Any, workdir: Any) -> Any:
        raise NotImplementedError(self._reason)

    def cleanup(self) -> None:
        return None


# Map of stub scaffolds → human-readable status pointing at the spec.
_STUB_REASONS: dict[str, str] = {
    "opencode": (
        "opencode runner pending; uses OpenAI-compat wire under its own "
        "scaffold prompts. See P1.8."
    ),
    "hermes-agent": (
        "hermes-agent runner pending; Nous Research Hermes agentic loop."
    ),
    "nanobot": "nanobot runner pending; minimal-scaffold variant.",
    "cursor": "cursor runner pending; Cursor IDE agent harness.",
}


def make_runner(
    *,
    runner: str,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    is_local: bool | None = None,
    system_prompt: str | None = None,
    **extra: Any,
) -> BaseRunner:
    """Construct a runner for the given (runner_id, model_id).

    Parameters:
        runner: scaffold id (``claude-code`` | ``mock`` | ``anthropic-compat``
            | ``openai-compat`` | ``local`` | a stub id).
        model: model id from ``MODEL_REGISTRY`` (or a custom name — the
            factory falls back gracefully for unregistered models).
        api_key: override env-var lookup. Omit for ``local`` (Ollama
            doesn't authenticate by default).
        base_url: override the wire base URL. Defaults are derived from
            the model's registry entry (vendor / scaffold).
        is_local: force the local flag. Defaults: True if the model is
            tagged ``local`` in the registry, OR runner=="local".
        system_prompt: passed through to the constructed runner (compat
            runners use it as the API ``system`` field).
        **extra: forwarded to the runner constructor as-is.

    Returns a :class:`BaseRunner` ready for ``prepare()`` → ``run_task()``.
    """
    info = get_model_info(model)
    local = (
        is_local
        if is_local is not None
        else (runner == "local" or (info is not None and info.local))
    )

    if runner == "mock":
        return MockRunner(**extra)

    if runner == "claude-code":
        # ClaudeCodeRunner uses the CLI; api_key is irrelevant here.
        return ClaudeCodeRunner(model=model, **extra)

    if runner == "codex-cli":
        # CodexCLIRunner shells out to `codex exec --json`; api_key irrelevant.
        # ``effort`` maps to Codex's model_reasoning_effort config key.
        effort = extra.pop("effort", None) or extra.pop("reasoning_effort", None)
        return CodexCLIRunner(model=model, reasoning_effort=effort, **extra)

    if runner == "gemini-cli":
        # GeminiCLIRunner shells out to `gemini --output-format stream-json`;
        # OAuth or env (GEMINI_API_KEY / GOOGLE_GENAI_USE_VERTEXAI /
        # _USE_GCA) is consumed by the binary itself — api_key irrelevant.
        # Accept reasoning_effort for API symmetry; runner warn-logs.
        effort = extra.pop("effort", None) or extra.pop("reasoning_effort", None)
        return GeminiCLIRunner(model=model, reasoning_effort=effort, **extra)

    if runner == "pi-agent":
        # PiAgentRunner shells out to `pi --mode json --print`; vendor API
        # keys are consumed by the binary itself via env (ANTHROPIC_API_KEY,
        # OPENAI_API_KEY, etc.) — api_key irrelevant on the runner.
        # ``effort`` maps to Pi's --thinking levels (off/minimal/low/medium/
        # high/xhigh).
        effort = extra.pop("effort", None) or extra.pop("reasoning_effort", None)
        return PiAgentRunner(model=model, effort=effort, **extra)

    if runner == "local" or local:
        resolved_base = base_url or (
            extra.pop("scaffold", None) and local_base_url(extra.pop("scaffold", ""))
        ) or local_base_url("ollama")
        # Local endpoints commonly don't authenticate; allow empty key.
        return OpenAICompatRunner(
            model=model,
            api_key=api_key if api_key is not None else "",
            base_url=resolved_base,
            is_local=True,
            system_prompt=system_prompt,
            **extra,
        )

    if runner == "anthropic-compat":
        vendor = extra.pop("vendor", None) or (info.family if info else "anthropic")
        resolved_base = base_url or vendor_base_url(vendor)
        return AnthropicCompatRunner(
            model=model,
            api_key=api_key,
            base_url=resolved_base,
            system_prompt=system_prompt,
            **extra,
        )

    if runner == "openai-compat":
        return OpenAICompatRunner(
            model=model,
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
            system_prompt=system_prompt,
            **extra,
        )

    # Stub family
    if runner in _STUB_REASONS:
        return StubRunner(scaffold=runner, model=model, reason=_STUB_REASONS[runner])

    raise ValueError(f"unknown runner: {runner!r}")


def supported_runners() -> list[str]:
    """All runner ids the factory knows about. Stubs included.

    Order is roughly "most stable first" so CLI help reads well.
    """
    return [
        "mock",
        "claude-code",
        "anthropic-compat",
        "openai-compat",
        "local",
        # stubs
        "codex-cli",
        "gemini-cli",
        "opencode",
        "pi-agent",
        "hermes-agent",
        "nanobot",
        "cursor",
    ]


__all__ = ["StubRunner", "make_runner", "supported_runners"]
