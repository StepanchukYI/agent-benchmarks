"""Codex CLI adapter — normalizes `codex exec --json` JSONL events into the trajectory protocol.

Mirrors ``claude_code.py`` in structure (subprocess.Popen, stream-by-line JSON parse,
workdir/home scrubbing, TrajectoryWriter wiring), but adapts to Codex's
different event shape.

Codex event model (verified 2026-05-21 against codex-cli 0.132.0):

* Codex emits NDJSON to stdout when ``--json`` is passed. The outer envelope
  is ``{"type": "<kind>", ...}`` where ``<kind>`` is one of:
  ``thread.started`` (first), ``turn.started``, ``turn.completed`` (success,
  carries ``usage``), ``turn.failed`` (carries an error reason), ``item.started``,
  ``item.completed``, ``error``.
* Tool calls are NOT separate ``tool_call`` / ``tool_result`` events like
  Claude Code. Instead, Codex emits ``item.started`` followed by
  ``item.completed`` for each unit of work, with the ``item.type`` field
  distinguishing the kind: ``command_execution``, ``agent_message``,
  ``mcp_tool_call``, ``file_change``, ``reasoning``, ``plan_update``,
  ``web_search``, ``error``.
* Usage is delivered exactly once via ``turn.completed.usage`` with keys
  ``input_tokens``, ``cached_input_tokens``, ``output_tokens``,
  ``reasoning_output_tokens``.
* Reasoning effort is not a CLI flag; it is set via the generic ``-c key=val``
  override (``-c model_reasoning_effort=high``). See ``_build_argv`` below.
* Codex does not expose a ``--system-prompt`` / ``--append-system-prompt``
  flag. To match ``claude_code.py``'s sandbox prompt injection we prepend
  the sandbox system prompt to the user prompt (recorded verbatim in
  ``run_start.system_prompt_verbatim``). ``AGENTS.md`` is intentionally
  ignored: tests run with ``--skip-git-repo-check`` outside any repo,
  and ``--ephemeral`` is set so the session never persists.
"""

from __future__ import annotations

import contextlib
import json
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

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


_DEFAULT_DATASET_VERSION = "ab-datasets==0.0.1"

# Identical to the Claude Code sandbox prompt. Kept verbatim for parity so
# scorers comparing system_prompt_verbatim across runners see the same text.
_SANDBOX_SYSTEM_PROMPT = (
    "You are an isolated benchmark agent. The only valid scope of your work "
    "is the current working directory. Do not read or write any path outside "
    "the cwd. Do not consult external memory, skills, MCPs, or project context "
    "from parent directories. Treat the task description below as the sole "
    "specification. Do not ask questions; produce the requested artifact(s) "
    "directly. When the task is complete, stop."
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _scrub_workdir(value: Any, workdir_abs: str) -> Any:
    """Recursively replace occurrences of workdir absolute path with `./` form."""
    if not workdir_abs:
        return value
    prefix = workdir_abs + "/"
    if isinstance(value, str):
        if value == workdir_abs:
            return "."
        if value.startswith(prefix):
            return "./" + value[len(prefix):]
        return value.replace(prefix, "./").replace(workdir_abs, ".")
    if isinstance(value, dict):
        return {k: _scrub_workdir(v, workdir_abs) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_workdir(v, workdir_abs) for v in value]
    if isinstance(value, tuple):
        return tuple(_scrub_workdir(v, workdir_abs) for v in value)
    return value


def _scrub_home(value: Any, home_abs: str) -> Any:
    """Recursively replace occurrences of the user home absolute path with `~`."""
    if not home_abs:
        return value
    prefix = home_abs + "/"
    if isinstance(value, str):
        if value == home_abs:
            return "~"
        if value.startswith(prefix):
            return "~/" + value[len(prefix):]
        return value.replace(prefix, "~/").replace(home_abs, "~")
    if isinstance(value, dict):
        return {k: _scrub_home(v, home_abs) for k, v in value.items()}
    if isinstance(value, list):
        return [_scrub_home(v, home_abs) for v in value]
    if isinstance(value, tuple):
        return tuple(_scrub_home(v, home_abs) for v in value)
    return value


def _scrub_turn(turn: dict[str, Any], workdir_abs: str) -> dict[str, Any]:
    """Scrub workdir paths from tool_calls[].args and tool_returns[] strings."""
    home_abs = str(Path.home())
    tool_calls = turn.get("tool_calls") or []
    for tc in tool_calls:
        if isinstance(tc, dict) and "args" in tc:
            scrubbed = _scrub_workdir(tc.get("args"), workdir_abs)
            tc["args"] = _scrub_home(scrubbed, home_abs)
    tool_returns = turn.get("tool_returns") or []
    for i, tr in enumerate(tool_returns):
        if isinstance(tr, dict):
            tool_returns[i] = {
                k: _scrub_home(_scrub_workdir(v, workdir_abs), home_abs)
                for k, v in tr.items()
            }
    if isinstance(turn.get("model_output"), str):
        out = _scrub_workdir(turn["model_output"], workdir_abs)
        turn["model_output"] = _scrub_home(out, home_abs)
    return turn


def _resolve_codex_version(binary: str = "codex") -> str:
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
                # Output looks like "codex-cli 0.132.0". Take last whitespace-separated token.
                return f"codex-cli@{line.split()[-1]}"
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    return "codex-cli@unknown"


class CodexCLIRunner(BaseRunner):
    """Drives the `codex exec --json` CLI and normalizes events into the trajectory protocol."""

    def __init__(
        self,
        model: str = "gpt-5.4",
        binary: str = "codex",
        reasoning_effort: str | None = None,
        extra_args: list[str] | None = None,
        dataset_version: str = _DEFAULT_DATASET_VERSION,
        prompt_template_hash: str | None = None,
    ) -> None:
        self._model = model
        self._binary = binary
        self._reasoning_effort = reasoning_effort
        self._extra_args = list(extra_args or [])
        self._dataset_version = dataset_version
        self._prompt_template_hash = prompt_template_hash
        self._tier_manifest: Any | None = None
        self._proc: subprocess.Popen | None = None
        self._cached_version: str | None = None
        # Subprocess isolation — see _isolation.py. Created per-run, released
        # in cleanup(). Without this, ~/.codex/ user config leaks into the
        # subprocess and arbitrary env tokens reach the agent.
        self._isolated_env: Any = None

    def name(self) -> str:
        return "codex-cli"

    def version(self) -> str:
        if self._cached_version is None:
            self._cached_version = _resolve_codex_version(self._binary)
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
        # Note flag positioning: ``--ask-for-approval`` lives on the parent ``codex``
        # command, NOT on ``exec`` (verified against codex 0.132.0 ``--help``). The
        # sandbox / model / json flags live on the ``exec`` subcommand.
        argv: list[str] = [
            self._binary,
            "--ask-for-approval",
            "never",
            "exec",
            "--json",
            "--sandbox",
            "workspace-write",
            "--skip-git-repo-check",
            "--ephemeral",
            "--strict-config",
            "-c",
            "shell_environment_policy.inherit=core",
            "--model",
            self._model,
        ]
        # Reasoning effort has no dedicated CLI flag in current codex-cli; the
        # documented way is the generic config override ``-c key=value``.
        if self._reasoning_effort:
            argv.extend(["-c", f"model_reasoning_effort={self._reasoning_effort}"])
        argv.extend(self._extra_args)
        # Prompt is the trailing positional. Codex also accepts stdin via "-",
        # but a positional argument is cleaner and unambiguous when the prompt
        # is short. We still write the prompt via stdin below if it's long;
        # see run_task() for the stdin path.
        argv.append("-")  # ← read prompt from stdin
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
        if info is None:
            return None
        return info.context_window or None

    def run_task(
        self,
        task: Any,
        trajectory_writer: TrajectoryWriter,
        workdir: Path | None = None,
    ) -> Any:
        from ab_datasets.schemas import RunStatus  # local import avoids cycle

        if workdir is None:
            raise ValueError("workdir is required")
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        workdir_abs = str(workdir.resolve())

        # Codex has no --append-system-prompt; prepend the sandbox prompt to the
        # user prompt so we still get the parity behavior with claude_code.
        task_prompt = build_prompt(task)
        full_prompt = _SANDBOX_SYSTEM_PROMPT + "\n\n" + task_prompt

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
            "system_prompt_verbatim": _SANDBOX_SYSTEM_PROMPT,
        }
        if self._reasoning_effort:
            run_start_payload["reasoning"] = {"effort": self._reasoning_effort}
        ctx = self._context_window()
        if ctx:
            run_start_payload["model_context_window_tokens"] = ctx
        trajectory_writer.write_run_start(run_start_payload)

        before_snapshot = snapshot(workdir)

        # Isolation barrier — see _isolation.py. Preserve real HOME so
        # codex's ChatGPT Plus/Pro subscription auth (~/.codex/auth.json
        # + macOS keychain "OpenAI Codex") stays reachable. Env whitelist
        # strips secret operator env vars (OBSIDIAN_/workplace SaaS/etc). Per-run config
        # overrides via --strict-config + -c shell_environment_policy.inherit
        # = core block ~/.codex/config.toml from injecting arbitrary tool
        # rules into the agent's session.
        self._isolated_env = IsolatedEnv.build(use_fake_home=False)
        argv = self._build_argv()

        # Spawn defensively: if the binary is missing, write a clean run_end
        # with status=error rather than letting the FileNotFoundError bubble
        # up through the harness. Symmetric with claude_code's behavior.
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
        except (FileNotFoundError, OSError) as exc:
            self._write_run_end(
                trajectory_writer,
                status=RunStatus.error.value,
                totals_tokens_in=0,
                totals_tokens_out=0,
                totals_latency_ms=0,
                totals_cost=0.0,
            )
            _ = exc
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

        if self._proc.stdin is not None:
            try:
                self._proc.stdin.write(full_prompt)
                self._proc.stdin.close()
            except (BrokenPipeError, OSError):
                pass

        idx = 0
        last_event_ts = time.monotonic()
        totals_tokens_in = 0
        totals_tokens_out = 0
        totals_latency_ms = 0
        # Per-item bookkeeping: a command_execution emits item.started THEN
        # item.completed; we buffer the started in flight so we can pair its
        # call (→ tool_calls on assistant turn) with the result (→ tool_returns
        # on a tool turn).
        pending_calls: dict[str, dict[str, Any]] = {}
        terminal_status: str | None = None
        agent_text_collected: list[str] = []
        # Accumulate tool_calls + agent message into one assistant turn per
        # turn.started ... turn.completed boundary.
        current_turn_tool_calls: list[dict[str, Any]] = []
        current_turn_started: bool = False

        def _flush_assistant_turn(*, latency_ms: int) -> None:
            nonlocal idx, current_turn_tool_calls
            if not current_turn_started and not current_turn_tool_calls and not agent_text_collected:
                return
            turn_payload = {
                "idx": idx,
                "role": "assistant",
                "prompt_delta": None,
                "tool_calls": list(current_turn_tool_calls),
                "tool_returns": [],
                "model_output": "\n".join(agent_text_collected),
                "vault_state_diff": None,
                "tokens_in": 0,
                "tokens_out": 0,
                "latency_ms": latency_ms,
                "cost_usd": 0.0,
            }
            trajectory_writer.write_turn(_scrub_turn(turn_payload, workdir_abs))
            idx += 1
            current_turn_tool_calls = []
            agent_text_collected.clear()

        try:
            assert self._proc.stdout is not None
            for raw_line in self._proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Codex occasionally interleaves stack traces / warnings on
                    # stdout when something goes wrong. Skip non-JSON cleanly.
                    continue
                if not isinstance(event, dict):
                    continue

                etype = event.get("type")
                now = time.monotonic()
                latency_ms = int((now - last_event_ts) * 1000)
                last_event_ts = now

                if etype == "thread.started":
                    continue

                if etype == "turn.started":
                    current_turn_started = True
                    continue

                if etype == "item.started":
                    item = event.get("item") or {}
                    itype = item.get("item_type") or item.get("type")
                    item_id = item.get("id") or f"item-{len(pending_calls)}"
                    if itype == "command_execution":
                        call_entry = {
                            "id": item_id,
                            "name": "shell",
                            "args": {"command": item.get("command", "")},
                        }
                        pending_calls[item_id] = call_entry
                        current_turn_tool_calls.append(call_entry)
                    elif itype == "mcp_tool_call":
                        call_entry = {
                            "id": item_id,
                            "name": item.get("name") or item.get("tool") or "mcp",
                            "args": item.get("arguments") or item.get("input") or {},
                        }
                        pending_calls[item_id] = call_entry
                        current_turn_tool_calls.append(call_entry)
                    elif itype == "file_change":
                        call_entry = {
                            "id": item_id,
                            "name": "file_change",
                            "args": {
                                "path": item.get("path") or item.get("file_path") or "",
                                "kind": item.get("kind") or item.get("change_kind"),
                            },
                        }
                        pending_calls[item_id] = call_entry
                        current_turn_tool_calls.append(call_entry)
                    # other item kinds (reasoning, plan_update, web_search) are
                    # not modelled as tool calls; ignore start.
                    continue

                if etype == "item.completed":
                    item = event.get("item") or {}
                    itype = item.get("item_type") or item.get("type")
                    item_id = item.get("id") or ""
                    if itype == "agent_message":
                        text = item.get("text") or ""
                        if text:
                            agent_text_collected.append(text)
                        continue
                    if itype == "error":
                        # Surface error as a tool-result-shaped entry so it
                        # doesn't get silently dropped.
                        msg = item.get("message") or item.get("text") or ""
                        tool_returns = [
                            {
                                "tool_use_id": item_id or "error",
                                "is_error": True,
                                "detail": msg,
                            }
                        ]
                        tool_turn = {
                            "idx": idx,
                            "role": "tool",
                            "prompt_delta": None,
                            "tool_calls": [],
                            "tool_returns": tool_returns,
                            "model_output": "",
                            "vault_state_diff": None,
                            "tokens_in": 0,
                            "tokens_out": 0,
                            "latency_ms": latency_ms,
                            "cost_usd": 0.0,
                        }
                        trajectory_writer.write_turn(_scrub_turn(tool_turn, workdir_abs))
                        idx += 1
                        continue
                    # Pair tool-call completion with a tool turn.
                    if itype in {"command_execution", "mcp_tool_call", "file_change"}:
                        detail: str
                        if itype == "command_execution":
                            detail = str(item.get("aggregated_output") or item.get("output") or "")
                        elif itype == "mcp_tool_call":
                            result = item.get("result") or item.get("output")
                            detail = json.dumps(result, ensure_ascii=False) if not isinstance(result, str) else result
                            if detail is None:
                                detail = ""
                        else:  # file_change
                            detail = str(item.get("status") or item.get("result") or "")
                        is_error = False
                        if itype == "command_execution":
                            exit_code = item.get("exit_code")
                            is_error = bool(exit_code) and exit_code != 0
                        # If the command_execution status is "failed", mark error.
                        if item.get("status") == "failed":
                            is_error = True
                        tool_returns = [
                            {
                                "tool_use_id": item_id,
                                "is_error": is_error,
                                "detail": detail,
                            }
                        ]
                        # Flush any open assistant turn first so the tool turn
                        # appears strictly after its triggering tool_call (the
                        # trajectory validator requires monotonic idx and the
                        # call-first/return-second invariant downstream).
                        if current_turn_tool_calls or agent_text_collected or current_turn_started:
                            _flush_assistant_turn(latency_ms=0)
                            current_turn_started = False
                        tool_turn = {
                            "idx": idx,
                            "role": "tool",
                            "prompt_delta": None,
                            "tool_calls": [],
                            "tool_returns": tool_returns,
                            "model_output": "",
                            "vault_state_diff": None,
                            "tokens_in": 0,
                            "tokens_out": 0,
                            "latency_ms": latency_ms,
                            "cost_usd": 0.0,
                        }
                        trajectory_writer.write_turn(_scrub_turn(tool_turn, workdir_abs))
                        idx += 1
                        pending_calls.pop(item_id, None)
                        continue
                    # Unknown item type: ignore.
                    continue

                if etype == "turn.completed":
                    usage = event.get("usage") or {}
                    if isinstance(usage, dict):
                        totals_tokens_in += int(usage.get("input_tokens") or 0)
                        totals_tokens_out += int(usage.get("output_tokens") or 0)
                        totals_tokens_out += int(usage.get("reasoning_output_tokens") or 0)
                    totals_latency_ms += latency_ms
                    # Flush the assistant turn that this turn.completed terminated.
                    _flush_assistant_turn(latency_ms=latency_ms)
                    current_turn_started = False
                    terminal_status = "completed"
                    continue

                if etype == "turn.failed":
                    _flush_assistant_turn(latency_ms=latency_ms)
                    current_turn_started = False
                    terminal_status = "error"
                    continue

                if etype == "error":
                    terminal_status = "error"
                    continue

            self._proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _flush_assistant_turn(latency_ms=0)
            self.cleanup()
            status_obj = RunStatus.timeout
            self._write_run_end(
                trajectory_writer,
                status=status_obj.value,
                totals_tokens_in=totals_tokens_in,
                totals_tokens_out=totals_tokens_out,
                totals_latency_ms=totals_latency_ms,
                totals_cost=estimate_cost_usd(self._model, totals_tokens_in, totals_tokens_out),
            )
            return status_obj
        except Exception:
            with contextlib.suppress(Exception):
                _flush_assistant_turn(latency_ms=0)
            with contextlib.suppress(Exception):
                self._write_run_end(
                    trajectory_writer,
                    status=RunStatus.error.value,
                    totals_tokens_in=totals_tokens_in,
                    totals_tokens_out=totals_tokens_out,
                    totals_latency_ms=totals_latency_ms,
                    totals_cost=estimate_cost_usd(self._model, totals_tokens_in, totals_tokens_out),
                )
            raise

        # Final flush if a turn ended without an explicit turn.completed.
        after_snapshot = snapshot(workdir)
        vault_diff = diff(before_snapshot, after_snapshot)
        if current_turn_tool_calls or agent_text_collected:
            if any(vault_diff.values()):
                # Build a buffered turn with diff attached, then write it.
                turn_payload = {
                    "idx": idx,
                    "role": "assistant",
                    "prompt_delta": None,
                    "tool_calls": list(current_turn_tool_calls),
                    "tool_returns": [],
                    "model_output": "\n".join(agent_text_collected),
                    "vault_state_diff": vault_diff,
                    "tokens_in": 0,
                    "tokens_out": 0,
                    "latency_ms": 0,
                    "cost_usd": 0.0,
                }
                trajectory_writer.write_turn(_scrub_turn(turn_payload, workdir_abs))
                idx += 1
                current_turn_tool_calls = []
                agent_text_collected.clear()
            else:
                _flush_assistant_turn(latency_ms=0)
        elif any(vault_diff.values()) and idx > 0:
            # No buffered turn but files changed — emit a minimal trailing
            # assistant turn carrying the diff so scorers can see it.
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
        if terminal_status == "completed":
            status_obj = RunStatus.completed
        elif terminal_status == "error":
            status_obj = RunStatus.error
        else:
            status_obj = RunStatus.completed if rc == 0 else RunStatus.error

        totals_cost = estimate_cost_usd(self._model, totals_tokens_in, totals_tokens_out)
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
