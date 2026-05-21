"""Claude Code CLI adapter — normalizes `claude --output-format stream-json` into the trajectory protocol."""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import threading
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from ab_harness.pricing import estimate_cost_usd
from ab_harness.runners._prompt import build_prompt
from ab_harness.runners._vault_diff import diff, snapshot
from ab_harness.runners.base import BaseRunner

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


_DEFAULT_DATASET_VERSION = "ab-datasets==0.0.1"

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
    return turn


def _resolve_claude_version() -> str:
    try:
        result = subprocess.run(
            ["claude", "--version"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            out = (result.stdout or result.stderr).strip().splitlines()[0] if (result.stdout or result.stderr) else ""
            if out:
                return f"claude-code-cli@{out.split()[0]}"
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    return "claude-code-cli@unknown"


class ClaudeCodeRunner(BaseRunner):
    """Drives the `claude` CLI in headless stream-json mode and normalizes events."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-5",
        binary: str = "claude",
        extra_args: list[str] | None = None,
        dataset_version: str = _DEFAULT_DATASET_VERSION,
        prompt_template_hash: str | None = None,
        effort: str | None = None,
        env_overrides: dict[str, str] | None = None,
    ) -> None:
        self._model = model
        self._binary = binary
        self._extra_args = list(extra_args or [])
        self._dataset_version = dataset_version
        self._prompt_template_hash = prompt_template_hash
        # Maps to claude CLI's --effort. Recorded in trajectory.reasoning.
        # Valid values per `claude --help`: low|medium|high|xhigh|max.
        self._effort = effort
        # Per-run env overrides — set on the subprocess on top of
        # os.environ.copy(). Use this to point claude CLI at any
        # Anthropic-compat endpoint (Zhipu GLM, MiniMax, Kimi, DeepSeek)
        # without touching the user's shell config:
        #   env_overrides={
        #     "ANTHROPIC_BASE_URL": "https://api.z.ai/api/anthropic",
        #     "ANTHROPIC_AUTH_TOKEN": "<token>",
        #     "ANTHROPIC_MODEL": "GLM-5.1",
        #   }
        # Auth tokens MUST come from the caller; this class doesn't read
        # vendor-specific env (no AUTH_TOKEN_GLM auto-lookup) — privacy
        # boundary: we never imprint operator credentials into commits.
        self._env_overrides = dict(env_overrides or {})
        self._tier_manifest: Any | None = None
        self._proc: subprocess.Popen | None = None
        self._cached_version: str | None = None

    def name(self) -> str:
        return "claude-code-cli"

    def version(self) -> str:
        if self._cached_version is None:
            self._cached_version = _resolve_claude_version()
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

    def _build_argv(self) -> list[str]:
        argv = [
            self._binary,
            "--print",
            "--output-format",
            "stream-json",
            "--verbose",
            "--dangerously-skip-permissions",
            "--model",
            self._model,
            "--append-system-prompt",
            _SANDBOX_SYSTEM_PROMPT,
        ]
        if self._effort:
            argv.extend(["--effort", self._effort])
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
        sha = getattr(self._tier_manifest, "total_sha256", None)
        if sha is None and isinstance(self._tier_manifest, dict):
            sha = self._tier_manifest.get("total_sha256")
        return sha

    def run_task(
        self,
        task: Any,
        trajectory_writer: TrajectoryWriter,
        workdir: Path | None = None,
    ) -> Any:
        from ab_datasets.schemas import RunStatus  # local import to avoid cycle at module load

        if workdir is None:
            raise ValueError("workdir is required")
        workdir = Path(workdir)
        workdir.mkdir(parents=True, exist_ok=True)
        workdir_abs = str(workdir.resolve())

        prompt = build_prompt(task)
        run_id = f"run-{uuid.uuid4().hex[:12]}"
        task_id = getattr(task, "id", None) or "unknown"

        # Look up the model's context window so the leaderboard can warn
        # about window-exhaustion failures separately from capability ones.
        # See docs/result-sensitivity-axes.md axis #7.
        try:
            from ab_harness.models import get_model_info

            _model_info = get_model_info(self._model)
            _ctx_window = _model_info.context_window if _model_info else None
        except Exception:
            _ctx_window = None

        started_at = _utc_now_iso()
        trajectory_writer.write_run_start(
            {
                "run_id": run_id,
                "task_id": task_id,
                "model": self._model,
                "harness": self.version(),
                "tier": self._tier_value(),
                "tier_hash": self._tier_hash(),
                "dataset_version": self._dataset_version,
                "prompt_template_hash": self._prompt_template_hash,
                "started_at": started_at,
                # Sensitivity-axis fields (additive, all optional). See
                # docs/result-sensitivity-axes.md for what each captures.
                "sampling": None,  # claude CLI doesn't expose temperature flags
                "reasoning": (
                    {"effort": self._effort, "budget_tokens": None}
                    if self._effort
                    else None
                ),
                "system_prompt_verbatim": _SANDBOX_SYSTEM_PROMPT,
                "model_context_window_tokens": _ctx_window,
                "output_truncated": None,
                "output_tokens_used": None,
                "turn_cap": None,
            }
        )

        before_snapshot = snapshot(workdir)

        env = os.environ.copy()
        # Per-runner env overrides (e.g. ANTHROPIC_BASE_URL +
        # ANTHROPIC_AUTH_TOKEN for vendor-routed Anthropic-compat
        # endpoints). Applied on top of os.environ.copy() so caller
        # always wins over the user's shell.
        if self._env_overrides:
            env.update(self._env_overrides)
        argv = self._build_argv()
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
        totals_cost = 0.0
        totals_latency_ms = 0
        result_event: dict[str, Any] | None = None
        stream_seen_system = False
        buffered_assistant: dict[str, Any] | None = None
        run_end_written = False

        try:
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                line = line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue

                etype = event.get("type")
                now = time.monotonic()
                latency_ms = int((now - last_event_ts) * 1000)
                last_event_ts = now

                if etype == "system":
                    stream_seen_system = True
                    continue

                if etype == "assistant":
                    if buffered_assistant is not None:
                        trajectory_writer.write_turn(_scrub_turn(buffered_assistant, workdir_abs))
                        idx += 1
                    buffered_assistant = self._build_assistant_turn(event, idx, latency_ms)
                    totals_tokens_in += buffered_assistant["tokens_in"]
                    totals_tokens_out += buffered_assistant["tokens_out"]
                    totals_cost += buffered_assistant["cost_usd"]
                    totals_latency_ms += buffered_assistant["latency_ms"]
                    continue

                if etype == "user":
                    if buffered_assistant is not None:
                        trajectory_writer.write_turn(_scrub_turn(buffered_assistant, workdir_abs))
                        idx += 1
                        buffered_assistant = None
                    turn_payload = self._build_user_tool_turn(event, idx, latency_ms)
                    trajectory_writer.write_turn(_scrub_turn(turn_payload, workdir_abs))
                    totals_latency_ms += turn_payload["latency_ms"]
                    idx += 1
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
                totals_cost=totals_cost,
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
                    totals_cost=totals_cost,
                )
            run_end_written = True
            raise

        _ = stream_seen_system

        after_snapshot = snapshot(workdir)
        vault_diff = diff(before_snapshot, after_snapshot)
        if buffered_assistant is not None:
            if any(vault_diff.values()):
                buffered_assistant["vault_state_diff"] = vault_diff
            trajectory_writer.write_turn(_scrub_turn(buffered_assistant, workdir_abs))
            idx += 1
            buffered_assistant = None

        if result_event is not None:
            subtype = result_event.get("subtype", "")
            if subtype == "success":
                status = RunStatus.completed
            elif subtype.startswith("error"):
                status = RunStatus.error
            else:
                status = RunStatus.completed
            cost_from_result = float(result_event.get("total_cost_usd") or 0.0)
            if cost_from_result > totals_cost:
                totals_cost = cost_from_result
            usage = result_event.get("usage") or {}
            if isinstance(usage, dict):
                totals_tokens_in = max(totals_tokens_in, int(usage.get("input_tokens") or 0))
                totals_tokens_out = max(totals_tokens_out, int(usage.get("output_tokens") or 0))
            duration_ms = int(result_event.get("duration_ms") or 0)
            if duration_ms:
                totals_latency_ms = duration_ms
            if totals_cost == 0.0 and (totals_tokens_in > 0 or totals_tokens_out > 0):
                totals_cost = estimate_cost_usd(self._model, totals_tokens_in, totals_tokens_out)
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

    def _build_assistant_turn(self, event: dict[str, Any], idx: int, latency_ms: int) -> dict[str, Any]:
        message = event.get("message") or {}
        content_blocks = message.get("content") or []
        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text", ""))
            elif btype == "tool_use":
                tool_calls.append(
                    {
                        "id": block.get("id"),
                        "name": block.get("name"),
                        "args": block.get("input") or {},
                    }
                )
        usage = message.get("usage") or {}
        tokens_in = int(usage.get("input_tokens") or 0)
        tokens_out = int(usage.get("output_tokens") or 0)
        cost = float(event.get("cost_usd") or message.get("cost_usd") or 0.0)
        if cost == 0.0 and (tokens_in > 0 or tokens_out > 0):
            cost = estimate_cost_usd(self._model, tokens_in, tokens_out)
        return {
            "idx": idx,
            "role": "assistant",
            "prompt_delta": None,
            "tool_calls": tool_calls,
            "tool_returns": [],
            "model_output": "\n".join(p for p in text_parts if p),
            "vault_state_diff": None,
            "tokens_in": tokens_in,
            "tokens_out": tokens_out,
            "latency_ms": latency_ms,
            "cost_usd": cost,
        }

    def _build_user_tool_turn(self, event: dict[str, Any], idx: int, latency_ms: int) -> dict[str, Any]:
        message = event.get("message") or {}
        content_blocks = message.get("content") or []
        tool_returns: list[dict[str, Any]] = []
        for block in content_blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") != "tool_result":
                continue
            content = block.get("content")
            detail: str
            if isinstance(content, list):
                detail = "".join(
                    (c.get("text") or "") for c in content if isinstance(c, dict)
                )
            else:
                detail = str(content or "")
            tool_returns.append(
                {
                    "tool_use_id": block.get("tool_use_id"),
                    "is_error": bool(block.get("is_error", False)),
                    "detail": detail,
                }
            )
        return {
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
