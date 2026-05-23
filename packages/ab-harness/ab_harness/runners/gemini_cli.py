"""Gemini CLI adapter — normalizes `gemini --output-format stream-json` into the trajectory protocol.

Wire shape verified 2026-05-21 against `@google/gemini-cli@0.20.2` source
(``stream-json-formatter.js`` + ``nonInteractiveCli.js``). The CLI emits
JSONL events to stdout in this order:

1. ``init`` — ``{type, timestamp, session_id, model}``
2. ``message`` (role=user) — the prompt as-sent
3. zero or more ``message`` (role=assistant, ``delta:true``) chunks,
   interleaved with ``tool_use`` / ``tool_result`` events
4. ``result`` — terminal event with aggregated ``stats``

Differences from Claude Code's ``stream-json``:

* Assistant text arrives as many ``delta:true`` ``message`` events; we
  buffer them into one assistant turn so the trajectory doesn't explode
  into one-token turns.
* Tool calls live in their own ``tool_use`` event (not inside an
  ``assistant`` message), so we flush the buffered text first, then
  append the tool call as part of the same assistant turn if the tool
  arrives between text chunks. Tool results come back as ``tool_result``
  events with ``tool_id`` matching the call's id.
* No per-event cost — only token totals in the final ``result.stats``.
  We backfill cost via ``ab_harness.pricing.estimate_cost_usd`` for the
  whole run (assigned to the last assistant turn) so leaderboards stay
  comparable across runners.
* No ``--effort`` / reasoning-budget flag in 0.20.2; constructor accepts
  ``reasoning_effort`` for API symmetry but warn-logs and drops it.
* System prompt: Gemini CLI has no ``--append-system-prompt`` flag. It
  reads ``GEMINI.md`` from the cwd (the same convention as Claude Code's
  ``CLAUDE.md``). We write the sandbox system prompt to ``GEMINI.md`` in
  the workdir before invocation. If a ``GEMINI.md`` already exists we
  prepend our sandbox lines so the operator's file is preserved.
"""

from __future__ import annotations

import contextlib
import json
import logging
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ab_harness.models import get_model_info
from ab_harness.pricing import estimate_cost_usd
from ab_harness.runners._isolation import IsolatedEnv
from ab_harness.runners._prompt import build_prompt
from ab_harness.runners._vault_diff import diff, snapshot
from ab_harness.runners.base import BaseRunner
from ab_harness.runners.base import compose_system_prompt as _compose_system_prompt
from ab_harness.runners.claude_code import _scrub_turn

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


_logger = logging.getLogger(__name__)

_DEFAULT_DATASET_VERSION = "ab-datasets==0.0.1"

# Mirrors the constant in claude_code.py so the two runners stay isolated
# even though they share the spirit. Kept local on purpose: if the Claude
# prompt drifts we don't want Gemini to silently follow.
_SANDBOX_SYSTEM_PROMPT = (
    "You are an isolated benchmark agent. The only valid scope of your work "
    "is the current working directory. Do not read or write any path outside "
    "the cwd. Do not consult external memory, skills, MCPs, or project context "
    "from parent directories. Treat the task description below as the sole "
    "specification. Do not ask questions; produce the requested artifact(s) "
    "directly. When the task is complete, stop."
)

_SANDBOX_HEADER_MARKER = "<!-- ab-harness sandbox preamble (do not edit) -->"


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_gemini_version(binary: str = "gemini") -> str:
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            raw = (result.stdout or result.stderr).strip().splitlines()
            if raw:
                token = raw[0].split()[0]
                return f"gemini-cli@{token}"
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    return "gemini-cli@unknown"


def _write_sandbox_gemini_md(workdir: Path) -> None:
    """Write the sandbox system prompt as GEMINI.md in the workdir.

    Gemini CLI auto-loads GEMINI.md from cwd; this is its only documented
    system-prompt injection mechanism in 0.20.x. If a GEMINI.md already
    exists, we prepend our sandbox preamble so the operator's file (or
    a fixture-provided one for T1+ tiers) is preserved verbatim below.
    """
    target = workdir / "GEMINI.md"
    preamble = f"{_SANDBOX_HEADER_MARKER}\n{_SANDBOX_SYSTEM_PROMPT}\n"
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if _SANDBOX_HEADER_MARKER in existing:
            return
        target.write_text(preamble + "\n" + existing, encoding="utf-8")
    else:
        target.write_text(preamble, encoding="utf-8")


class GeminiCLIRunner(BaseRunner):
    """Drives the `gemini` CLI in stream-json mode and normalizes events.

    Spawns the binary with ``--output-format stream-json --yolo --model M``,
    feeds the prompt via stdin (no positional argv to dodge argv-length
    limits on long L2/L3 prompts), and translates Gemini's JSONL event
    stream into ``ab-harness`` trajectory turns.
    """

    def __init__(
        self,
        model: str = "gemini-3-pro",
        binary: str = "gemini",
        extra_args: list[str] | None = None,
        dataset_version: str = _DEFAULT_DATASET_VERSION,
        prompt_template_hash: str | None = None,
        reasoning_effort: str | None = None,
        prompt_label: str | None = None,
    ) -> None:
        self._model = model
        self._binary = binary
        self._extra_args = list(extra_args or [])
        self._dataset_version = dataset_version
        self._prompt_template_hash = prompt_template_hash
        self._prompt_label = prompt_label
        # Gemini CLI 0.20.x has no reasoning-budget flag. Accept the
        # kwarg for symmetry with ClaudeCodeRunner.effort but warn-log
        # and drop it so callers see we noticed.
        if reasoning_effort:
            _logger.warning(
                "GeminiCLIRunner: reasoning_effort=%r ignored — Gemini CLI 0.20.x "
                "exposes no --effort / --thinking-budget flag.",
                reasoning_effort,
            )
        self._reasoning_effort = reasoning_effort
        self._tier_manifest: Any | None = None
        self._proc: subprocess.Popen | None = None
        self._cached_version: str | None = None
        # Subprocess isolation — see _isolation.py. Without this the gemini
        # CLI auto-loads ~/.gemini/ user config and the operator's
        # GOOGLE_*/GEMINI_* env (plus arbitrary tokens) reach the agent.
        self._isolated_env: Any = None

    def name(self) -> str:
        return "gemini-cli"

    def version(self) -> str:
        if self._cached_version is None:
            self._cached_version = _resolve_gemini_version(self._binary)
        return self._cached_version

    def prepare(self, tier_manifest: Any) -> None:
        self._tier_manifest = tier_manifest

    def cleanup(self) -> None:
        if self._proc is not None and self._proc.poll() is None:
            with contextlib.suppress(OSError):
                self._proc.kill()
            with contextlib.suppress(subprocess.TimeoutExpired, OSError):
                self._proc.wait(timeout=5)
        if self._proc is not None:
            for stream in (self._proc.stdout, self._proc.stderr, self._proc.stdin):
                if stream is not None:
                    with contextlib.suppress(OSError):
                        stream.close()
        self._proc = None
        if self._isolated_env is not None:
            with contextlib.suppress(OSError):
                self._isolated_env.cleanup()
            self._isolated_env = None

    def _build_argv(self) -> list[str]:
        # Gemini CLI flags verified against 0.20.2 `gemini --help`.
        # --yolo = auto-approve all tool calls (analog of Claude Code's
        # --dangerously-skip-permissions). No --non-interactive flag
        # exists; non-interactive is implied by `-p/--prompt` or
        # stdin-piped input.
        #
        # Isolation: ``-e __ab_isolated__`` passes an extension name that
        # doesn't exist, which gemini interprets as "use these extensions"
        # → matches none → no extensions loaded. This blocks user-installed
        # extensions from contaminating the agent. ``--include-directories``
        # not used (cwd=/tmp/<run>/workdir already scopes context).
        #
        # KNOWN LIMITATION: gemini-cli does not expose a flag to suppress
        # ~/.gemini/settings.json or a user-level GEMINI.md load. For full
        # isolation with non-subscription auth, set GEMINI_API_KEY directly
        # and the operator can opt into `use_fake_home=True` via env
        # (AB_GEMINI_ISOLATE_HOME=1) in a future patch.
        argv = [
            self._binary,
            "--output-format",
            "stream-json",
            "--model",
            self._model,
            "--yolo",
            "-e",
            "__ab_isolated__",
        ]
        argv.extend(self._extra_args)
        return argv

    def _tier_value(self) -> str:
        if self._tier_manifest is None:
            return "T0"
        tier = getattr(self._tier_manifest, "tier", None)
        if tier is None and isinstance(self._tier_manifest, dict):
            tier = self._tier_manifest.get("tier")
        return getattr(tier, "value", None) or (tier if isinstance(tier, str) else "T0")

    def _tier_hash(self) -> str | None:
        if self._tier_manifest is None:
            return None
        sha = getattr(self._tier_manifest, "total_sha256", None) or getattr(
            self._tier_manifest, "tier_hash", None
        )
        if sha is None and isinstance(self._tier_manifest, dict):
            sha = self._tier_manifest.get("total_sha256") or self._tier_manifest.get(
                "tier_hash"
            )
        return sha

    def _claude_md_text(self) -> str | None:
        if self._tier_manifest is None:
            return None
        text = getattr(self._tier_manifest, "claude_md_text", None)
        if text is None and isinstance(self._tier_manifest, dict):
            text = self._tier_manifest.get("claude_md_text")
        return text

    def _context_window(self) -> int | None:
        info = get_model_info(self._model)
        if info is None or not info.context_window:
            return None
        return info.context_window

    def run_task(
        self,
        task: Any,
        trajectory_writer: TrajectoryWriter,
        workdir: Path | None = None,
    ) -> Any:
        from ab_datasets.schemas import RunStatus  # local import to avoid cycle

        if workdir is None:
            raise ValueError("workdir is required")
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        workdir_abs = str(workdir.resolve())

        # Stage the sandbox system prompt as GEMINI.md before the CLI
        # spawns; the binary picks it up automatically from cwd.
        _write_sandbox_gemini_md(workdir)

        prompt = build_prompt(task)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        task_id = getattr(task, "id", None) or "unknown"

        started_at = _utc_now_iso()
        run_start_payload: dict[str, Any] = {
            "run_id": run_id,
            "task_id": task_id,
            "model": self._model,
            "harness": self.version(),
            "tier": self._tier_value(),
            "tier_hash": self._tier_hash(),
            "dataset_version": self._dataset_version,
            "prompt_template_hash": self._prompt_template_hash,
            "prompt_label": self._prompt_label,
            "started_at": started_at,
            # Sensitivity-axis fields. Gemini CLI 0.20.x exposes no
            # temperature/top-p/max-output knobs on the CLI itself
            # (everything defaults to backend defaults), so we leave
            # sampling fields None and only record what's recoverable.
            "sampling": {
                "temperature": None,
                "top_p": None,
                "top_k": None,
                "max_output_tokens": None,
                "stream": True,
            },
            "reasoning": {
                "effort": None,
                "budget_tokens": None,
            },
            "system_prompt_verbatim": _compose_system_prompt(
                _SANDBOX_SYSTEM_PROMPT, self._claude_md_text()
            ),
            "model_context_window_tokens": self._context_window(),
        }
        trajectory_writer.write_run_start(run_start_payload)

        before_snapshot = snapshot(workdir)

        # Isolation barrier — see _isolation.py. Preserve real HOME so
        # gemini's Google OAuth login state (~/.gemini/oauth_creds.json)
        # stays reachable. Env whitelist strips secret env vars
        # (OBSIDIAN_/workplace SaaS tokens/etc). User-level memory blocked at the argv
        # layer via `-e` (empty extension list) — see _build_argv.
        self._isolated_env = IsolatedEnv.build(use_fake_home=False)
        argv = self._build_argv()
        try:
            self._proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(workdir),
                env=self._isolated_env.env,
                text=True,
                bufsize=1,
            )
        except FileNotFoundError:
            # Binary missing on this host — surface a clean unrunnable
            # status instead of a Python crash. The CLI prints a
            # helpful "command not found" already; we just record it.
            self._write_run_end(
                trajectory_writer,
                status=RunStatus.unrunnable.value,
                totals_tokens_in=0,
                totals_tokens_out=0,
                totals_latency_ms=0,
                totals_cost=0.0,
            )
            return RunStatus.unrunnable

        def _drain_stderr() -> None:
            if self._proc is None or self._proc.stderr is None:
                return
            try:
                for _ in self._proc.stderr:
                    pass
            except (OSError, ValueError):
                pass

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        if self._proc.stdin is not None:
            try:
                self._proc.stdin.write(prompt)
                self._proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        idx = 0
        last_event_ts = time.monotonic()
        totals_tokens_in = 0
        totals_tokens_out = 0
        totals_latency_ms = 0
        result_event: dict[str, Any] | None = None
        # Streaming assistant turn under construction: gemini emits
        # assistant text in many delta:true chunks and tool calls in
        # separate tool_use events. We accumulate into one logical turn
        # and flush when the next tool_result arrives or at stream end.
        buffered_assistant: dict[str, Any] | None = None
        run_end_written = False

        def _ensure_assistant_turn() -> dict[str, Any]:
            nonlocal buffered_assistant
            if buffered_assistant is None:
                buffered_assistant = {
                    "idx": idx,
                    "role": "assistant",
                    "prompt_delta": None,
                    "tool_calls": [],
                    "tool_returns": [],
                    "model_output": "",
                    "vault_state_diff": None,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "latency_ms": 0,
                    "cost_usd": 0.0,
                }
            return buffered_assistant

        try:
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Gemini occasionally interleaves a stderr-style
                    # warning on stdout when the model misbehaves; drop
                    # non-JSON lines defensively.
                    continue

                etype = event.get("type")
                now = time.monotonic()
                latency_ms = int((now - last_event_ts) * 1000)
                last_event_ts = now

                if etype == "init":
                    # Session metadata; nothing to record beyond the
                    # already-written run_start.
                    continue

                if etype == "message":
                    role = event.get("role")
                    if role == "user":
                        # Echo of our own prompt; skip — we have the
                        # task description in run_start already.
                        continue
                    if role == "assistant":
                        turn = _ensure_assistant_turn()
                        chunk = event.get("content") or ""
                        turn["model_output"] += chunk
                        turn["latency_ms"] += latency_ms
                    continue

                if etype == "tool_use":
                    turn = _ensure_assistant_turn()
                    turn["tool_calls"].append(
                        {
                            "id": event.get("tool_id"),
                            "name": event.get("tool_name"),
                            "args": event.get("parameters") or {},
                        }
                    )
                    turn["latency_ms"] += latency_ms
                    continue

                if etype == "tool_result":
                    # Flush the buffered assistant turn first so the
                    # tool-return arrives in its own turn (matching the
                    # Claude Code shape: assistant turn, then tool turn).
                    if buffered_assistant is not None:
                        trajectory_writer.write_turn(
                            _scrub_turn(buffered_assistant, workdir_abs)
                        )
                        idx += 1
                        buffered_assistant = None
                    err = event.get("error") or {}
                    is_error = event.get("status") == "error"
                    detail: str
                    if is_error:
                        detail = err.get("message") or event.get("output") or ""
                    else:
                        detail = event.get("output") or ""
                    tool_turn = {
                        "idx": idx,
                        "role": "tool",
                        "prompt_delta": None,
                        "tool_calls": [],
                        "tool_returns": [
                            {
                                "tool_use_id": event.get("tool_id"),
                                "is_error": is_error,
                                "detail": detail,
                            }
                        ],
                        "model_output": "",
                        "vault_state_diff": None,
                        "tokens_in": 0,
                        "tokens_out": 0,
                        "latency_ms": latency_ms,
                        "cost_usd": 0.0,
                    }
                    trajectory_writer.write_turn(_scrub_turn(tool_turn, workdir_abs))
                    totals_latency_ms += latency_ms
                    idx += 1
                    continue

                if etype == "error":
                    # Non-fatal warnings: log to the buffered turn so
                    # the trajectory captures them, but don't break.
                    turn = _ensure_assistant_turn()
                    msg = event.get("message") or ""
                    if msg:
                        sep = "\n" if turn["model_output"] else ""
                        turn["model_output"] += f"{sep}[gemini-cli error] {msg}"
                    continue

                if etype == "result":
                    result_event = event
                    break

            self._proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            if buffered_assistant is not None:
                trajectory_writer.write_turn(_scrub_turn(buffered_assistant, workdir_abs))
                idx += 1
                buffered_assistant = None
            self.cleanup()
            status = RunStatus.timeout
            self._write_run_end(
                trajectory_writer,
                status=status.value,
                totals_tokens_in=totals_tokens_in,
                totals_tokens_out=totals_tokens_out,
                totals_latency_ms=totals_latency_ms,
                totals_cost=0.0,
            )
            run_end_written = True
            return status
        except Exception:
            if buffered_assistant is not None:
                with contextlib.suppress(Exception):
                    trajectory_writer.write_turn(_scrub_turn(buffered_assistant, workdir_abs))
                buffered_assistant = None
            with contextlib.suppress(Exception):
                self._write_run_end(
                    trajectory_writer,
                    status=RunStatus.error.value,
                    totals_tokens_in=totals_tokens_in,
                    totals_tokens_out=totals_tokens_out,
                    totals_latency_ms=totals_latency_ms,
                    totals_cost=0.0,
                )
            run_end_written = True
            raise

        # Stream ended (normally or because we saw `result`).
        after_snapshot = snapshot(workdir)
        vault_diff = diff(before_snapshot, after_snapshot)

        # Apply totals from the final result event (the only place
        # Gemini exposes aggregate token counts in stream-json mode).
        totals_cost = 0.0
        if result_event is not None:
            stats = result_event.get("stats") or {}
            if isinstance(stats, dict):
                totals_tokens_in = max(totals_tokens_in, int(stats.get("input_tokens") or 0))
                totals_tokens_out = max(totals_tokens_out, int(stats.get("output_tokens") or 0))
                duration_ms = int(stats.get("duration_ms") or 0)
                if duration_ms:
                    totals_latency_ms = duration_ms

        if totals_tokens_in > 0 or totals_tokens_out > 0:
            # Gemini CLI under OAuth (free tier) emits no cost; backfill
            # from the local pricing table so leaderboards stay
            # comparable across runners. Aliases are resolved by
            # estimate_cost_usd's prefix fallback.
            totals_cost = estimate_cost_usd(self._model, totals_tokens_in, totals_tokens_out)

        # Pin totals onto the last assistant turn so per-turn rollups
        # still sum to the run total (single-source-of-truth invariant).
        if buffered_assistant is not None:
            if any(vault_diff.values()):
                buffered_assistant["vault_state_diff"] = vault_diff
            buffered_assistant["tokens_in"] = totals_tokens_in
            buffered_assistant["tokens_out"] = totals_tokens_out
            buffered_assistant["cost_usd"] = totals_cost
            trajectory_writer.write_turn(_scrub_turn(buffered_assistant, workdir_abs))
            idx += 1
            buffered_assistant = None

        if result_event is not None:
            res_status = result_event.get("status")
            if res_status == "success":
                status = RunStatus.completed
            elif res_status == "error":
                status = RunStatus.error
            else:
                status = RunStatus.completed
        else:
            rc = self._proc.poll() if self._proc is not None else 1
            status = RunStatus.completed if rc == 0 else RunStatus.error

        self._write_run_end(
            trajectory_writer,
            status=status.value,
            totals_tokens_in=totals_tokens_in,
            totals_tokens_out=totals_tokens_out,
            totals_latency_ms=totals_latency_ms,
            totals_cost=totals_cost,
        )
        run_end_written = True
        _ = run_end_written
        return status

    @staticmethod
    def _write_run_end(
        writer: TrajectoryWriter,
        *,
        status: str,
        totals_tokens_in: int,
        totals_tokens_out: int,
        totals_latency_ms: int,
        totals_cost: float,
    ) -> None:
        writer.write_run_end(
            {
                "finished_at": _utc_now_iso(),
                "status": status,
                "totals": {
                    "tokens_in": totals_tokens_in,
                    "tokens_out": totals_tokens_out,
                    "latency_ms": totals_latency_ms,
                    "cost_usd": totals_cost,
                    "score": 0.0,
                },
            }
        )
