"""Pi CLI adapter — normalizes `pi --mode json --print` JSONL events into the trajectory protocol.

Mirrors ``claude_code.py`` / ``codex_cli.py`` / ``gemini_cli.py`` in structure
(subprocess.Popen, stream-by-line JSON parse, workdir/home scrubbing,
TrajectoryWriter wiring), but adapts to Pi's event shape.

Pi CLI surface (per https://github.com/earendil-works/pi, package
``@earendil-works/pi-coding-agent``):

    pi --mode json --print \\
       --model <provider/model> --provider <name> \\
       --thinking <off|minimal|low|medium|high|xhigh> \\
       --system-prompt <text> --append-system-prompt <text> \\
       --no-session "<prompt>"

* ``--mode json`` → one JSON event per line on stdout.
* ``--print`` (``-p``) → one-shot, no TUI.
* ``--no-session`` → ephemeral, no persisted history.
* ``--thinking`` levels match the harness `effort` strings 1:1
  (``off|minimal|low|medium|high|xhigh``).
* ``--system-prompt`` replaces the default framing entirely;
  ``--append-system-prompt`` adds to it — we use the latter so Pi's own
  agent framing is preserved while we still inject the sandbox preamble.

Event model (observed in @earendil-works/pi-coding-agent v0.1.x JSON
streaming output — verified against package README + source as of
2026-05-21):

* Outer envelope: ``{"type": "<kind>", ...}``. Kinds seen:
  - ``session``     — initial metadata (session_id, model, provider).
  - ``thinking``    — interleaved CoT chunks (we accumulate, do NOT emit
    as turns; trajectory does not include reasoning bodies).
  - ``message``     — assistant text (role=assistant, may stream as
    chunks with ``delta:true`` or arrive complete).
  - ``tool_use``    — model-issued tool call. ``{id,name,input}``.
  - ``tool_result`` — runtime result for a prior tool_use.
    ``{tool_use_id,output,is_error?}``.
  - ``usage``       — token totals; emitted at least once near the end.
  - ``result``      — terminal envelope with ``status`` and possibly
    aggregate usage / duration.
  - ``error``       — non-fatal warning or fatal error.

The runner buffers assistant text + tool_use into a single assistant
turn, then flushes on the first tool_result (or at stream end). This
keeps the trajectory's call-first/return-second invariant intact: one
assistant turn carrying tool_calls, immediately followed by a tool turn
carrying tool_returns.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ab_harness.models import get_model_info
from ab_harness.pricing import estimate_cost_usd
from ab_harness.runners._prompt import build_prompt
from ab_harness.runners._vault_diff import diff, snapshot
from ab_harness.runners.base import BaseRunner
from ab_harness.runners.claude_code import _scrub_turn

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


_logger = logging.getLogger(__name__)

_DEFAULT_DATASET_VERSION = "ab-datasets==0.0.1"

# Identical to the Claude Code / Codex / Gemini sandbox prompt. Kept
# verbatim so scorers comparing system_prompt_verbatim across runners
# see the same text.
_SANDBOX_SYSTEM_PROMPT = (
    "You are an isolated benchmark agent. The only valid scope of your work "
    "is the current working directory. Do not read or write any path outside "
    "the cwd. Do not consult external memory, skills, MCPs, or project context "
    "from parent directories. Treat the task description below as the sole "
    "specification. Do not ask questions; produce the requested artifact(s) "
    "directly. When the task is complete, stop."
)

# Pi CLI accepts these thinking levels (verified against
# @earendil-works/pi-coding-agent --help, 2026-05-21).
_PI_THINKING_LEVELS: frozenset[str] = frozenset(
    {"off", "minimal", "low", "medium", "high", "xhigh"}
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_pi_version(binary: str = "pi") -> str:
    try:
        result = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            stream = result.stdout or result.stderr or ""
            line = stream.strip().splitlines()[0] if stream.strip() else ""
            if line:
                # Output typically looks like "pi-coding-agent 0.1.4" or "0.1.4".
                token = line.split()[-1]
                return f"pi-agent@{token}"
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    return "pi-agent@unknown"


class PiAgentRunner(BaseRunner):
    """Drives the `pi` CLI in `--mode json --print` mode and normalizes events.

    Spawns the binary with ``--mode json --print --no-session
    --append-system-prompt <sandbox> --model M [--provider P]
    [--thinking L]``, feeds the user prompt as the trailing positional
    arg (Pi's documented one-shot path; we keep the binary's own framing
    intact via --append-system-prompt rather than --system-prompt).
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-7",
        binary: str = "pi",
        provider: str | None = None,
        effort: str | None = None,
        extra_args: list[str] | None = None,
        dataset_version: str = _DEFAULT_DATASET_VERSION,
        prompt_template_hash: str | None = None,
        env_overrides: dict[str, str] | None = None,
    ) -> None:
        self._model = model
        self._binary = binary
        self._provider = provider
        # Map of harness effort → Pi --thinking. Identity mapping if the
        # caller already passes a valid Pi level. We accept anything but
        # only forward valid levels to the CLI (unknown values are
        # warn-logged and dropped so we don't crash an otherwise-good run).
        if effort and effort not in _PI_THINKING_LEVELS:
            _logger.warning(
                "PiAgentRunner: effort=%r not in Pi's --thinking levels %s; "
                "dropping from argv but still recording in trajectory.",
                effort,
                sorted(_PI_THINKING_LEVELS),
            )
        self._effort = effort
        self._extra_args = list(extra_args or [])
        self._dataset_version = dataset_version
        self._prompt_template_hash = prompt_template_hash
        # Per-run env overrides — applied on top of os.environ.copy().
        # Use this for vendor API keys (e.g. ANTHROPIC_API_KEY,
        # OPENAI_API_KEY) without imprinting them in committed code.
        self._env_overrides = dict(env_overrides or {})
        self._tier_manifest: Any | None = None
        self._proc: subprocess.Popen | None = None
        self._cached_version: str | None = None

    def name(self) -> str:
        return "pi-agent"

    def version(self) -> str:
        if self._cached_version is None:
            self._cached_version = _resolve_pi_version(self._binary)
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

    def _build_argv(self, prompt: str) -> list[str]:
        argv: list[str] = [
            self._binary,
            "--mode",
            "json",
            "--print",
            "--no-session",
            "--model",
            self._model,
            "--append-system-prompt",
            _SANDBOX_SYSTEM_PROMPT,
        ]
        if self._provider:
            argv.extend(["--provider", self._provider])
        if self._effort and self._effort in _PI_THINKING_LEVELS:
            argv.extend(["--thinking", self._effort])
        argv.extend(self._extra_args)
        # Pi's one-shot path takes the user prompt as the trailing
        # positional. Some prompts can be long; argv length on Linux is
        # ~2MB (ARG_MAX) so passing inline is fine for benchmark sizes.
        argv.append(prompt)
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
        sha = getattr(self._tier_manifest, "total_sha256", None)
        if sha is None and isinstance(self._tier_manifest, dict):
            sha = self._tier_manifest.get("total_sha256")
        return sha

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
            "started_at": started_at,
            # Pi CLI 0.1.x exposes no temperature/top-p/max-output flags;
            # everything defaults to backend defaults.
            "sampling": None,
            "reasoning": (
                {"effort": self._effort, "budget_tokens": None}
                if self._effort
                else None
            ),
            "system_prompt_verbatim": _SANDBOX_SYSTEM_PROMPT,
            "model_context_window_tokens": self._context_window(),
            "output_truncated": None,
            "output_tokens_used": None,
            "turn_cap": None,
        }
        trajectory_writer.write_run_start(run_start_payload)

        before_snapshot = snapshot(workdir)

        env = os.environ.copy()
        if self._env_overrides:
            env.update(self._env_overrides)
        argv = self._build_argv(prompt)

        # Spawn defensively: if the binary is missing, write a clean
        # run_end with status=error rather than letting the
        # FileNotFoundError bubble up through the harness. Matches
        # claude_code / codex_cli behavior on missing binary.
        try:
            self._proc = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=str(workdir),
                env=env,
                text=True,
                bufsize=1,
            )
        except (FileNotFoundError, OSError):
            self._write_run_end(
                trajectory_writer,
                status=RunStatus.error.value,
                totals_tokens_in=0,
                totals_tokens_out=0,
                totals_latency_ms=0,
                totals_cost=0.0,
            )
            return RunStatus.error

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

        # Pi reads the prompt from argv (one-shot positional), not stdin.
        # Close stdin so the child doesn't block waiting for input.
        if self._proc.stdin is not None:
            with contextlib.suppress(OSError):
                self._proc.stdin.close()

        idx = 0
        last_event_ts = time.monotonic()
        totals_tokens_in = 0
        totals_tokens_out = 0
        totals_latency_ms = 0
        result_event: dict[str, Any] | None = None
        terminal_status: str | None = None
        # Streaming assistant turn under construction: Pi may emit
        # assistant text in chunks and tool calls in separate events.
        # We accumulate into one logical turn and flush when the next
        # tool_result arrives or at stream end.
        buffered_assistant: dict[str, Any] | None = None

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
            for raw_line in self._proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Pi may interleave non-JSON warnings on stdout if
                    # the model/runtime misbehaves; drop defensively.
                    continue
                if not isinstance(event, dict):
                    continue

                etype = event.get("type")
                now = time.monotonic()
                latency_ms = int((now - last_event_ts) * 1000)
                last_event_ts = now

                if etype == "session":
                    # Session metadata; nothing to record beyond the
                    # already-written run_start.
                    continue

                if etype == "thinking":
                    # Pi emits chain-of-thought as a separate event
                    # kind. We intentionally do NOT include reasoning
                    # bodies in the trajectory (matches Claude Code /
                    # Gemini behavior). Discard.
                    continue

                if etype == "message":
                    role = event.get("role")
                    if role and role != "assistant":
                        # Echo of our own prompt or system; skip.
                        continue
                    turn = _ensure_assistant_turn()
                    # Pi may emit message content as either a string
                    # ("content") or a list of blocks. Accept both.
                    content = event.get("content")
                    chunk = ""
                    if isinstance(content, str):
                        chunk = content
                    elif isinstance(content, list):
                        chunk = "".join(
                            (b.get("text") or "")
                            for b in content
                            if isinstance(b, dict)
                        )
                    else:
                        # Fallback: some streams put text in "text".
                        chunk = str(event.get("text") or "")
                    if chunk:
                        turn["model_output"] += chunk
                    turn["latency_ms"] += latency_ms
                    continue

                if etype == "tool_use":
                    turn = _ensure_assistant_turn()
                    turn["tool_calls"].append(
                        {
                            "id": event.get("id") or event.get("tool_id"),
                            "name": event.get("name") or event.get("tool_name"),
                            "args": event.get("input")
                            or event.get("parameters")
                            or event.get("arguments")
                            or {},
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
                    is_error = bool(event.get("is_error", False))
                    if event.get("status") == "error":
                        is_error = True
                    raw_output = event.get("output")
                    if raw_output is None:
                        raw_output = event.get("content")
                    detail: str
                    if isinstance(raw_output, list):
                        detail = "".join(
                            (b.get("text") or "")
                            for b in raw_output
                            if isinstance(b, dict)
                        )
                    elif isinstance(raw_output, str):
                        detail = raw_output
                    elif raw_output is None:
                        # Pi may put errors in `error.message`.
                        err = event.get("error")
                        if isinstance(err, dict):
                            detail = err.get("message") or ""
                        else:
                            detail = ""
                    else:
                        detail = json.dumps(raw_output, ensure_ascii=False)
                    tool_turn = {
                        "idx": idx,
                        "role": "tool",
                        "prompt_delta": None,
                        "tool_calls": [],
                        "tool_returns": [
                            {
                                "tool_use_id": event.get("tool_use_id")
                                or event.get("tool_id")
                                or event.get("id"),
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

                if etype == "usage":
                    usage = event.get("usage") if isinstance(event.get("usage"), dict) else event
                    if isinstance(usage, dict):
                        totals_tokens_in = max(
                            totals_tokens_in, int(usage.get("input_tokens") or 0)
                        )
                        totals_tokens_out = max(
                            totals_tokens_out, int(usage.get("output_tokens") or 0)
                        )
                    continue

                if etype == "error":
                    # Non-fatal warnings: log to the buffered turn so
                    # the trajectory captures them, but don't break.
                    msg = ""
                    if isinstance(event.get("error"), dict):
                        msg = event["error"].get("message") or ""
                    msg = msg or event.get("message") or ""
                    if msg:
                        turn = _ensure_assistant_turn()
                        sep = "\n" if turn["model_output"] else ""
                        turn["model_output"] += f"{sep}[pi error] {msg}"
                    # A top-level `fatal:true` flag means the run died.
                    if event.get("fatal"):
                        terminal_status = "error"
                    continue

                if etype == "result":
                    result_event = event
                    break

            self._proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            if buffered_assistant is not None:
                trajectory_writer.write_turn(
                    _scrub_turn(buffered_assistant, workdir_abs)
                )
                idx += 1
                buffered_assistant = None
            self.cleanup()
            status_obj = RunStatus.timeout
            self._write_run_end(
                trajectory_writer,
                status=status_obj.value,
                totals_tokens_in=totals_tokens_in,
                totals_tokens_out=totals_tokens_out,
                totals_latency_ms=totals_latency_ms,
                totals_cost=estimate_cost_usd(
                    self._model, totals_tokens_in, totals_tokens_out
                ),
            )
            return status_obj
        except Exception:
            if buffered_assistant is not None:
                with contextlib.suppress(Exception):
                    trajectory_writer.write_turn(
                        _scrub_turn(buffered_assistant, workdir_abs)
                    )
                buffered_assistant = None
            with contextlib.suppress(Exception):
                self._write_run_end(
                    trajectory_writer,
                    status=RunStatus.error.value,
                    totals_tokens_in=totals_tokens_in,
                    totals_tokens_out=totals_tokens_out,
                    totals_latency_ms=totals_latency_ms,
                    totals_cost=estimate_cost_usd(
                        self._model, totals_tokens_in, totals_tokens_out
                    ),
                )
            raise

        # Stream ended (normally or because we saw `result`).
        after_snapshot = snapshot(workdir)
        vault_diff = diff(before_snapshot, after_snapshot)

        # Apply totals from the final result event (Pi's last word on
        # aggregate usage when present).
        if result_event is not None:
            usage = result_event.get("usage")
            if isinstance(usage, dict):
                totals_tokens_in = max(
                    totals_tokens_in, int(usage.get("input_tokens") or 0)
                )
                totals_tokens_out = max(
                    totals_tokens_out, int(usage.get("output_tokens") or 0)
                )
            duration_ms = int(result_event.get("duration_ms") or 0)
            if duration_ms:
                totals_latency_ms = duration_ms

        totals_cost = 0.0
        if totals_tokens_in > 0 or totals_tokens_out > 0:
            # Pi exposes no cost field; backfill from the local pricing
            # table so leaderboards stay comparable across runners.
            totals_cost = estimate_cost_usd(
                self._model, totals_tokens_in, totals_tokens_out
            )

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
        elif any(vault_diff.values()) and idx > 0:
            # No buffered turn but files changed — emit a minimal
            # trailing assistant turn carrying the diff so scorers can
            # see it.
            turn_payload = {
                "idx": idx,
                "role": "assistant",
                "prompt_delta": None,
                "tool_calls": [],
                "tool_returns": [],
                "model_output": "",
                "vault_state_diff": vault_diff,
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": 0,
                "cost_usd": 0.0,
            }
            trajectory_writer.write_turn(_scrub_turn(turn_payload, workdir_abs))
            idx += 1

        # Decide terminal status.
        rc = self._proc.poll() if self._proc is not None else 1
        if result_event is not None:
            res_status = (
                result_event.get("status")
                or result_event.get("subtype")
                or ""
            )
            if res_status in {"success", "completed", "ok"}:
                status_obj = RunStatus.completed
            elif res_status in {"error", "failed"} or str(res_status).startswith("error"):
                status_obj = RunStatus.error
            else:
                status_obj = RunStatus.completed
        elif terminal_status == "error":
            status_obj = RunStatus.error
        else:
            status_obj = RunStatus.completed if rc == 0 else RunStatus.error

        self._write_run_end(
            trajectory_writer,
            status=status_obj.value,
            totals_tokens_in=totals_tokens_in,
            totals_tokens_out=totals_tokens_out,
            totals_latency_ms=totals_latency_ms,
            totals_cost=totals_cost,
        )
        return status_obj

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
