"""Anthropic API wrapper with VCR-style content-addressed cache.

The cache is the default execution mode — tests + CI MUST replay from cache,
never hit the network. Set ``AB_LLM_JUDGE_LIVE=1`` to enable live mode (which
also writes back to the cache for future replays).

Cache layout::

    <cache_dir>/
      <sha256(model + prompt)>.json   # one record per unique prompt

Record schema::

    {
        "model": "claude-haiku-4-5",
        "prompt_sha256": "...",
        "request": {...},      # what we sent
        "response": {...},     # full API response body
        "recorded_at": "..."    # ISO timestamp
    }
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

_log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT_SEC = 30.0
_DEFAULT_BASE_URL = "https://api.anthropic.com"
_DEFAULT_VERSION = "2023-06-01"
_LIVE_ENV = "AB_LLM_JUDGE_LIVE"


class JudgeError(RuntimeError):
    """Judge call failed (transport, cache miss in replay mode, bad shape)."""


@dataclass(frozen=True)
class JudgeResponse:
    """Parsed judge output."""

    score: float
    pass_: bool
    reasoning: str
    raw_text: str
    model: str
    cached: bool


def _prompt_key(model: str, prompt: str) -> str:
    h = hashlib.sha256()
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(prompt.encode("utf-8"))
    return h.hexdigest()


def _cache_path(cache_dir: Path, model: str, prompt: str) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / f"{_prompt_key(model, prompt)}.json"


def _live_mode_enabled() -> bool:
    return os.environ.get(_LIVE_ENV) == "1"


class JudgeClient:
    """Minimal Anthropic /v1/messages client with cache-or-live behavior."""

    def __init__(
        self,
        *,
        api_key: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        version: str = _DEFAULT_VERSION,
        timeout_sec: float = _DEFAULT_TIMEOUT_SEC,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self._base_url = base_url.rstrip("/")
        self._version = version
        self._timeout_sec = timeout_sec
        self._http_client = http_client

    def call_live(
        self,
        *,
        model: str,
        prompt: str,
        max_tokens: int = 512,
        temperature: float = 0.0,
    ) -> dict[str, Any]:
        """Hit the real Anthropic API. Raises :class:`JudgeError` on transport.

        Caller is responsible for checking ``_live_mode_enabled()`` first;
        this method does NOT short-circuit on env. Useful for tests that
        want to assert "live mode is reachable" without setting the env
        globally.
        """
        if not self._api_key:
            raise JudgeError("ANTHROPIC_API_KEY not set; cannot call live judge")

        body = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "x-api-key": self._api_key,
            "anthropic-version": self._version,
            "content-type": "application/json",
        }
        client = self._http_client or httpx.Client(timeout=self._timeout_sec)
        try:
            response = client.post(
                f"{self._base_url}/v1/messages",
                json=body,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            raise JudgeError(f"transport: {exc}") from exc
        finally:
            if self._http_client is None:
                client.close()

        if response.status_code >= 400:
            raise JudgeError(
                f"anthropic {response.status_code}: {response.text[:300]}"
            )
        try:
            return response.json()
        except json.JSONDecodeError as exc:
            raise JudgeError(f"bad json from anthropic: {exc}") from exc


def _extract_assistant_text(api_response: dict[str, Any]) -> str:
    """Pull the assistant's text out of an Anthropic /v1/messages response."""
    content = api_response.get("content")
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "".join(parts)


def _parse_judge_output(raw: str) -> tuple[float, bool, str]:
    """Parse the JSON object we asked the judge to emit.

    Tolerant of leading/trailing whitespace and a stray code-fence — judges
    sometimes ignore the "no markdown" instruction. Raises JudgeError on
    anything else.
    """
    stripped = raw.strip()
    # Strip a leading/trailing code fence if present.
    if stripped.startswith("```"):
        # remove first line + last fence
        lines = stripped.splitlines()
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()

    try:
        obj = json.loads(stripped)
    except json.JSONDecodeError as exc:
        # As a last-ditch effort, find the first { and last } and try again.
        first = stripped.find("{")
        last = stripped.rfind("}")
        if first >= 0 and last > first:
            try:
                obj = json.loads(stripped[first : last + 1])
            except json.JSONDecodeError as exc2:
                raise JudgeError(
                    f"judge output not parseable as JSON: {exc2}"
                ) from exc2
        else:
            raise JudgeError(f"judge output not parseable as JSON: {exc}") from exc

    if not isinstance(obj, dict):
        raise JudgeError("judge output is not a JSON object")
    score = obj.get("score")
    reasoning = obj.get("reasoning") or ""
    pass_ = obj.get("pass")
    try:
        score = float(score)
    except (TypeError, ValueError) as exc:
        raise JudgeError(f"judge.score not a float: {score!r}") from exc
    if not (0.0 <= score <= 1.0):
        raise JudgeError(f"judge.score out of [0,1]: {score}")
    if pass_ is None:
        pass_ = score >= 0.5
    return float(score), bool(pass_), str(reasoning)


def judge_call(
    *,
    model: str,
    prompt: str,
    cache_dir: Path,
    client: JudgeClient | None = None,
    allow_live: bool | None = None,
) -> JudgeResponse:
    """Score one task via the judge. Cache-first, optional live fallback.

    ``allow_live=None`` (default) → consult ``AB_LLM_JUDGE_LIVE`` env. Set
    explicitly to override (test code passes ``False`` to be paranoid).
    """
    cache_dir = Path(cache_dir)
    cache_file = _cache_path(cache_dir, model, prompt)

    if cache_file.exists():
        try:
            record = json.loads(cache_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise JudgeError(f"corrupt cache file {cache_file}: {exc}") from exc
        raw_text = _extract_assistant_text(record.get("response") or {})
        score, pass_, reasoning = _parse_judge_output(raw_text)
        return JudgeResponse(
            score=score,
            pass_=pass_,
            reasoning=reasoning,
            raw_text=raw_text,
            model=model,
            cached=True,
        )

    # Cache miss.
    live = allow_live if allow_live is not None else _live_mode_enabled()
    if not live:
        raise JudgeError(
            f"judge cache miss for {cache_file.name}; "
            f"set {_LIVE_ENV}=1 to record (network call) or pre-record the fixture"
        )

    client = client or JudgeClient()
    api_response = client.call_live(model=model, prompt=prompt)
    record = {
        "model": model,
        "prompt_sha256": _prompt_key(model, prompt),
        "request": {"prompt_len": len(prompt)},
        "response": api_response,
        "recorded_at": datetime.now(UTC).isoformat(),
    }
    cache_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    _log.info("judge: recorded new cache entry at %s", cache_file)

    raw_text = _extract_assistant_text(api_response)
    score, pass_, reasoning = _parse_judge_output(raw_text)
    return JudgeResponse(
        score=score,
        pass_=pass_,
        reasoning=reasoning,
        raw_text=raw_text,
        model=model,
        cached=False,
    )


__all__ = [
    "JudgeClient",
    "JudgeError",
    "JudgeResponse",
    "judge_call",
]
