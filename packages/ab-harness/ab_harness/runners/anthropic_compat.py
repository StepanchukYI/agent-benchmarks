"""Generic /v1/messages runner — drives any Anthropic-compatible endpoint.

Used for:

* Anthropic Claude (default ``base_url=https://api.anthropic.com``).
* Chinese vendors that ship an Anthropic-compat layer: GLM (Zhipu),
  Kimi (Moonshot), Qwen (Alibaba), MiniMax. Operators set
  ``base_url`` + ``api_key`` per vendor; the wire shape stays the same.

This is NOT a CLI-scaffold runner (claude-code, codex-cli, etc.). It's a
direct API runner — handy for benchmarks that want to isolate "what does
the BASE MODEL do here" from "what does the scaffold add". Pair it with
the Inspect-AI bridge (P4.19) for orchestrated evals.

Mode of operation:

1. ``prepare(tier_manifest)`` stores the manifest. No network.
2. ``run_task(task, writer, workdir)`` builds a single user message from
   the task prompt (``build_prompt(task)``), posts /v1/messages, parses
   the assistant reply, writes a 3-event trajectory (run_start +
   single turn + run_end). Tool calls are NOT yet plumbed — this is
   the minimal runner, not the full agentic loop.
3. ``cleanup()`` closes the httpx client.

Why minimal first: full multi-turn tool-calling against a /v1/messages
endpoint requires re-implementing the agent loop (read tool_use blocks,
invoke tools, post tool_result back). That's a v2 — see
``packages/ab-harness/ab_harness/runners/_agent_loop.py`` placeholder
in a follow-up commit. The minimal runner is already useful for
"single-prompt completion" benchmarks (NIAH, format-following,
reasoning-without-tools).
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

_DEFAULT_BASE_URL = "https://api.anthropic.com"
_DEFAULT_VERSION = "2023-06-01"
_DEFAULT_TIMEOUT = 120.0
_DEFAULT_MAX_TOKENS = 4096


class AnthropicCompatRunner(BaseRunner):
    """Direct /v1/messages caller. One model, one prompt, one response.

    Construction params:
        model: model id (e.g. "claude-sonnet-4-5", "glm-4.5").
        api_key: API key. Reads ``ANTHROPIC_API_KEY`` env if omitted.
        base_url: API root. Defaults to Anthropic. Override per-vendor.
        version: ``anthropic-version`` header. Stable default.
        timeout_sec: HTTP timeout.
        max_tokens: response cap.
        system_prompt: optional system prompt.
        http_client: inject a fake for tests (or for shared connection pool).
    """

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        version: str = _DEFAULT_VERSION,
        timeout_sec: float = _DEFAULT_TIMEOUT,
        max_tokens: int = _DEFAULT_MAX_TOKENS,
        system_prompt: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._model = model
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._version = version
        self._timeout_sec = timeout_sec
        self._max_tokens = max_tokens
        self._system_prompt = system_prompt
        self._owned_http_client = http_client is None
        self._http_client = http_client
        self._tier_manifest: Any | None = None

    # ------------------------------------------------------------------
    # BaseRunner protocol
    # ------------------------------------------------------------------

    def name(self) -> str:
        return f"anthropic-compat({self._model})"

    def version(self) -> str:
        # The "version" string here is the wire protocol version, not the
        # tool. Stable so trajectory replay stays deterministic.
        return f"anthropic-compat@{self._version}"

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

        if not self._api_key:
            raise RuntimeError(
                "AnthropicCompatRunner: api_key required "
                "(pass api_key=... or set ANTHROPIC_API_KEY)"
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
                "dataset_version": "anthropic-compat==0.1",
                "prompt_template_hash": None,
                "started_at": started_at,
            }
        )

        t0 = time.monotonic()
        try:
            api_response = self._post_messages(prompt)
            assistant_text = _extract_text(api_response)
            usage = api_response.get("usage") or {}
            tokens_in = int(usage.get("input_tokens") or 0)
            tokens_out = int(usage.get("output_tokens") or 0)
            cost_usd = float(usage.get("cost_usd") or 0.0)
            if cost_usd == 0.0 and (tokens_in or tokens_out):
                cost_usd = estimate_cost_usd(self._model, tokens_in, tokens_out)
            latency_ms = int((time.monotonic() - t0) * 1000)
            status = RunStatus.completed
        except Exception as exc:
            _log.exception("anthropic-compat runner failed")
            assistant_text = ""
            tokens_in = 0
            tokens_out = 0
            cost_usd = 0.0
            latency_ms = int((time.monotonic() - t0) * 1000)
            status = RunStatus.failed
            api_response = {"error": str(exc)}

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

    def _post_messages(self, prompt: str) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self._model,
            "max_tokens": self._max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if self._system_prompt:
            body["system"] = self._system_prompt
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._version,
            "content-type": "application/json",
        }
        response = self._client().post(
            f"{self._base_url}/v1/messages",
            json=body,
            headers=headers,
        )
        if response.status_code >= 400:
            raise RuntimeError(
                f"anthropic-compat {response.status_code}: {response.text[:300]}"
            )
        return response.json()


def _now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _extract_text(api_response: dict[str, Any]) -> str:
    content = api_response.get("content")
    if not isinstance(content, list):
        return ""
    out: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                out.append(text)
    return "".join(out)


def _tier_value(tier_manifest: Any) -> str:
    if tier_manifest is None:
        return "T0"
    tier = getattr(tier_manifest, "tier", None)
    if tier is None and isinstance(tier_manifest, dict):
        tier = tier_manifest.get("tier")
    return getattr(tier, "value", None) or (
        tier if isinstance(tier, str) else "T0"
    )


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


__all__ = ["AnthropicCompatRunner"]


# Vendor presets — call site picks one and overrides api_key.
_VENDOR_BASE_URLS = {
    "anthropic": "https://api.anthropic.com",
    "zhipu": "https://open.bigmodel.cn/api/anthropic",
    "moonshot": "https://api.moonshot.cn/anthropic",
    "alibaba": "https://dashscope.aliyuncs.com/api/v2/apps/anthropic",
    "minimax": "https://api.minimax.chat/v1/anthropic",
}


def vendor_base_url(vendor: str) -> str:
    """Look up the Anthropic-compat base_url for a vendor key.

    Falls back to Anthropic's URL on unknown vendors so a typo doesn't
    silently route nowhere — the API call will fail loudly on auth.
    """
    return _VENDOR_BASE_URLS.get(vendor.lower(), _DEFAULT_BASE_URL)
