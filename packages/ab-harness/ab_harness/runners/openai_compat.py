"""Generic OpenAI-compatible runner — drives any /v1/chat/completions endpoint.

Single class covers:

* OpenAI (gpt-5, gpt-5-mini, o3, o4-mini) — default base_url.
* Self-hosted local scaffolds with OpenAI-compat APIs:
  - Ollama (``http://localhost:11434/v1``)
  - LM Studio (``http://localhost:1234/v1``)
  - vLLM (``http://localhost:8000/v1``)
  - llama.cpp HTTP server (``http://localhost:8080/v1``)
  - text-generation-webui (``http://localhost:5000/v1``)
* Any other vendor that exposes a chat-completions-shaped API.

Same trajectory protocol output as the Anthropic-compat runner; the
benchmark scoring layer doesn't care which wire shape the runner spoke.

Like ``AnthropicCompatRunner``, this is the minimal single-prompt runner
— no agentic tool-calling loop. Pair with the Inspect-AI bridge for
orchestration, or wait for the v2 agent-loop runner.
"""

from __future__ import annotations

import contextlib
import logging
import os
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from ab_harness.pricing import estimate_cost_usd
from ab_harness.runners._prompt import build_prompt
from ab_harness.runners.base import BaseRunner

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter

_log = logging.getLogger(__name__)

_DEFAULT_BASE_URL = "https://api.openai.com/v1"
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_MAX_TOKENS = 4096


class OpenAICompatRunner(BaseRunner):
    """Direct /v1/chat/completions caller. Single prompt → single response.

    Construction params:
        model: model id (e.g. "gpt-5", "gemma-3-27b", "qwen3-coder-32b-local").
        api_key: API key. Reads ``OPENAI_API_KEY`` env if omitted. Empty
            string allowed for unauthenticated local endpoints (Ollama).
        base_url: API root with trailing /v1. Defaults to OpenAI.
        timeout_sec: HTTP timeout.
        max_tokens: response cap.
        system_prompt: optional system prompt.
        is_local: if True, allow empty api_key (local scaffolds don't need
            one). Mostly cosmetic; the actual requirement is upstream-set.
        http_client: inject for tests / shared pool.
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_sec: float = _DEFAULT_TIMEOUT,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        system_prompt: str | None = None,
        is_local: bool = False,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._timeout_sec = timeout_sec
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        self._is_local = is_local
        self._owned_http_client = http_client is None
        self._http_client = http_client
        self._tier_manifest: Any | None = None

    # ------------------------------------------------------------------
    # BaseRunner protocol
    # ------------------------------------------------------------------

    def name(self) -> str:
        suffix = " (local)" if self._is_local else ""
        return f"openai-compat({self._model}){suffix}"

    def version(self) -> str:
        return "openai-compat@v1"

    def prepare(self, tier_manifest: Any) -> None:
        self._tier_manifest = tier_manifest

    def cleanup(self) -> None:
        if self._owned_http_client and self._http_client is not None:
            with contextlib.suppress(Exception):
                self._http_client.close()
            self._http_client = None

    def run_task(
        self,
        task: Any,
        trajectory_writer: TrajectoryWriter,
        workdir: Path,
    ) -> Any:
        from ab_datasets.schemas import RunStatus

        if not self._api_key and not self._is_local:
            raise RuntimeError(
                "OpenAICompatRunner: api_key required for non-local endpoints "
                "(pass api_key=... or set OPENAI_API_KEY; set is_local=True "
                "for self-hosted scaffolds that don't authenticate)"
            )

        run_id = f"run-{uuid.uuid4().hex[:12]}"
        task_id = getattr(task, "id", None) or "unknown"
        started_at = _now_iso()
        prompt = build_prompt(task)

        trajectory_writer.write_run_start(
            {
                "run_id": run_id,
                "task_id": task_id,
                "model": self._model,
                "harness": self.version(),
                "tier": _tier_value(self._tier_manifest),
                "tier_hash": _tier_hash(self._tier_manifest),
                "dataset_version": "openai-compat==0.1",
                "prompt_template_hash": None,
                "started_at": started_at,
            }
        )

        t0 = time.monotonic()
        try:
            api_response = self._post_chat(prompt)
            assistant_text = _extract_assistant_text(api_response)
            usage = api_response.get("usage") or {}
            # OpenAI: prompt_tokens / completion_tokens. Local scaffolds
            # sometimes use input_tokens / output_tokens; cover both.
            tokens_in = int(
                usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            )
            tokens_out = int(
                usage.get("completion_tokens") or usage.get("output_tokens") or 0
            )
            cost_usd = float(usage.get("cost_usd") or 0.0)
            if cost_usd == 0.0 and (tokens_in or tokens_out):
                cost_usd = estimate_cost_usd(self._model, tokens_in, tokens_out)
            latency_ms = int((time.monotonic() - t0) * 1000)
            status = RunStatus.completed
        except Exception:
            _log.exception("openai-compat runner failed")
            assistant_text = ""
            tokens_in = 0
            tokens_out = 0
            cost_usd = 0.0
            latency_ms = int((time.monotonic() - t0) * 1000)
            status = RunStatus.failed

        trajectory_writer.write_turn(
            {
                "idx": 0,
                "role": "assistant",
                "prompt_delta": prompt,
                "tool_calls": [],
                "tool_returns": [],
                "model_output": assistant_text,
                "vault_state_diff": None,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "latency_ms": latency_ms,
                "cost_usd": cost_usd,
            }
        )

        trajectory_writer.write_run_end(
            {
                "finished_at": _now_iso(),
                "status": status.value if hasattr(status, "value") else str(status),
                "totals": {
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                    "latency_ms": latency_ms,
                    "cost_usd": cost_usd,
                    "score": 0.0,
                },
            }
        )
        return status

    # ------------------------------------------------------------------
    # HTTP
    # ------------------------------------------------------------------

    def _client(self) -> httpx.Client:
        if self._http_client is None:
            self._http_client = httpx.Client(timeout=self._timeout_sec)
            self._owned_http_client = True
        return self._http_client

    def _post_chat(self, prompt: str) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if self._system_prompt:
            messages.append({"role": "system", "content": self._system_prompt})
        messages.append({"role": "user", "content": prompt})
        body: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": self._max_tokens,
        }
        headers: dict[str, str] = {"content-type": "application/json"}
        if self._api_key:
            headers["authorization"] = f"Bearer {self._api_key}"
        response = self._client().post(
            f"{self._base_url}/chat/completions",
            json=body,
            headers=headers,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"openai-compat {response.status_code}: {response.text[:300]}"
            )
        return response.json()


def _extract_assistant_text(api_response: dict[str, Any]) -> str:
    choices = api_response.get("choices") or []
    if not choices:
        return ""
    msg = choices[0].get("message") or {}
    content = msg.get("content")
    if isinstance(content, str):
        return content
    # vLLM / some local scaffolds return content as a list of blocks.
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts)
    return ""


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _tier_value(tier_manifest: Any) -> str:
    if tier_manifest is None:
        return "T0"
    tier = getattr(tier_manifest, "tier", None)
    if tier is None and isinstance(tier_manifest, dict):
        tier = tier_manifest.get("tier")
    return getattr(tier, "value", None) or (tier if isinstance(tier, str) else "T0")


def _tier_hash(tier_manifest: Any) -> str | None:
    if tier_manifest is None:
        return None
    # MaterializedTier exposes .tier_hash; a raw manifest exposes
    # .total_sha256. Check both so run_start.tier_hash is populated.
    sha = getattr(tier_manifest, "total_sha256", None) or getattr(
        tier_manifest, "tier_hash", None
    )
    if sha is None and isinstance(tier_manifest, dict):
        sha = tier_manifest.get("total_sha256") or tier_manifest.get("tier_hash")
    return sha


__all__ = ["OpenAICompatRunner"]
