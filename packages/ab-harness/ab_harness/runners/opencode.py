"""opencode CLI adapter — normalizes `opencode run --format json` into the trajectory protocol.

Mirrors ``claude_code.py`` and ``codex_cli.py`` in structure (subprocess.Popen,
stream-by-line JSON parse, workdir/home scrubbing, TrajectoryWriter wiring),
but adapts to opencode's defensive event-shape handling.

opencode CLI surface (per https://opencode.ai/docs/cli/, verified 2026-05-21):

* ``opencode run "<prompt>" --model <provider/model> --format json
  --dir <workdir> --dangerously-skip-permissions --thinking <level>``
* ``--format json`` emits NDJSON to stdout, one event per line. The exact
  schema is undocumented as of this writing, so this adapter reads lines
  defensively: any well-formed JSON object is inspected for common
  shapes (assistant text, tool calls, tool results, usage), and unknown
  event ``type`` values are logged-and-skipped without crashing.
* ``--thinking`` accepts ``off|minimal|low|medium|high|xhigh``. The runner
  maps ab-harness reasoning effort to this flag:
  ``low → low``, ``medium → medium``, ``high → high``, ``xhigh → xhigh``,
  ``max → xhigh`` (opencode tops out at xhigh; we treat ``max`` as the
  ceiling for symmetry with ClaudeCodeRunner).
* opencode has no documented ``--system-prompt`` / ``--append-system-prompt``
  flag. To match the sandbox-prompt parity with claude_code / codex_cli,
  this adapter writes the sandbox preamble to ``AGENTS.md`` in the workdir
  (opencode follows the Anthropic-led ``AGENTS.md`` convention; see
  ``OPENCODE_DISABLE_CLAUDE_CODE`` env note in the docs). If a file already
  exists, we prepend the sandbox lines so any operator/fixture content is
  preserved below.
* Pricing: if opencode emits per-event or aggregate usage tokens, we
  estimate cost via ``ab_harness.pricing.estimate_cost_usd``. If not, we
  leave the cost at 0 — never fake.

This adapter is intentionally pessimistic about opencode's event schema:
v0.x JSON output is not yet stable. Tests pin a canned stream so the
behavior is reproducible; production drift will surface as untriggered
branches (text → buffered assistant turn) rather than crashes.
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
from ab_harness.runners.claude_code import _scrub_turn

if TYPE_CHECKING:
    from ab_harness.trajectory.writer import TrajectoryWriter


_DEFAULT_DATASET_VERSION = "ab-datasets==0.0.1"

# Mirrors the constant in claude_code.py / codex_cli.py so the three
# runners stay isolated (no cross-import of the prompt string) even
# though they share the spirit. Kept local on purpose: if one runner's
# prompt drifts we don't want the others to silently follow.
_SANDBOX_SYSTEM_PROMPT = (
    "You are an isolated benchmark agent. The only valid scope of your work "
    "is the current working directory. Do not read or write any path outside "
    "the cwd. Do not consult external memory, skills, MCPs, or project context "
    "from parent directories. Treat the task description below as the sole "
    "specification. Do not ask questions; produce the requested artifact(s) "
    "directly. When the task is complete, stop."
)

_SANDBOX_HEADER_MARKER = "<!-- ab-harness sandbox preamble (do not edit) -->"

# Map ab-harness reasoning effort → opencode --thinking value.
# opencode's range tops at xhigh; "max" collapses there for symmetry with
# ClaudeCodeRunner's --effort vocabulary.
_EFFORT_TO_THINKING: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "high": "high",
    "xhigh": "xhigh",
    "max": "xhigh",
}


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _resolve_opencode_version(binary: str = "opencode") -> str:
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
                # Normalize "0.1.0" → "opencode@v0.1.0"; preserve a "v"
                # if the binary already includes one.
                ver = token if token.startswith("v") else f"v{token}"
                return f"opencode@{ver}"
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired):
        pass
    return "opencode@unknown"


def _write_sandbox_agents_md(workdir: Path) -> None:
    """Write the sandbox system prompt as AGENTS.md in the workdir.

    opencode follows the Anthropic-led ``AGENTS.md`` convention for
    agent-loadable instructions in a project root; this is its only
    documented system-prompt injection mechanism. If an AGENTS.md
    already exists (operator-provided or fixture-provided for T1+ tiers),
    we prepend our sandbox preamble so the existing content is preserved.
    """
    target = workdir / "AGENTS.md"
    preamble = f"{_SANDBOX_HEADER_MARKER}\n{_SANDBOX_SYSTEM_PROMPT}\n"
    if target.exists():
        existing = target.read_text(encoding="utf-8")
        if _SANDBOX_HEADER_MARKER in existing:
            return
        target.write_text(preamble + "\n" + existing, encoding="utf-8")
    else:
        target.write_text(preamble, encoding="utf-8")


class OpencodeRunner(BaseRunner):
    """Drives the `opencode run --format json` CLI and normalizes events.

    Spawns the binary, reads NDJSON from stdout line-by-line, and
    translates the event stream into ``ab-harness`` trajectory turns.
    Unknown event types are skipped defensively (opencode's stream
    schema is not yet stable as of v0.x).
    """

    def __init__(
        self,
        model: str = "anthropic/claude-sonnet-4-5",
        binary: str = "opencode",
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
        # ab-harness vocabulary: low|medium|high|xhigh|max. Maps to
        # opencode's --thinking via _EFFORT_TO_THINKING. We record the
        # caller's effort verbatim in trajectory.run_start.reasoning.effort
        # so leaderboards compare apples to apples across runners.
        self._effort = effort
        # Per-run env overrides — set on the subprocess on top of
        # os.environ.copy(). Used for vendor routing (e.g. pointing
        # opencode at a vendor-routed Anthropic/OpenAI endpoint via
        # ANTHROPIC_BASE_URL / OPENAI_BASE_URL without touching the
        # operator's shell). Caller is responsible for sourcing auth
        # tokens — this class never reads vendor-specific env on its
        # own (privacy boundary).
        self._env_overrides = dict(env_overrides or {})
        self._tier_manifest: Any | None = None
        self._proc: subprocess.Popen | None = None
        self._cached_version: str | None = None
        # Subprocess isolation — see _isolation.py. opencode auto-loads
        # ~/.config/opencode/ + ~/.local/share/opencode/, and the operator's
        # env carries arbitrary tokens. Drop both.
        self._isolated_env: Any = None

    def name(self) -> str:
        return "opencode"

    def version(self) -> str:
        if self._cached_version is None:
            self._cached_version = _resolve_opencode_version(self._binary)
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

    def _thinking_value(self) -> str | None:
        if not self._effort:
            return None
        return _EFFORT_TO_THINKING.get(self._effort)

    def _build_argv(self, *, workdir: Path) -> list[str]:
        # Per https://opencode.ai/docs/cli/ — `opencode run` accepts the
        # prompt as a positional, with --format/--model/--dir/--thinking
        # flags. We deliberately avoid passing the prompt as argv (long
        # L2/L3 prompts can blow past ARG_MAX) and feed via stdin with a
        # trailing "-" sentinel where supported; otherwise we fall back
        # to argv. opencode's CLI does NOT document a stdin sentinel, so
        # we pass the prompt as positional argv — see run_task below for
        # the trimmed safe-size handling.
        argv: list[str] = [
            self._binary,
            "run",
            "--format",
            "json",
            "--model",
            self._model,
            "--dir",
            str(workdir),
            "--dangerously-skip-permissions",
        ]
        thinking = self._thinking_value()
        if thinking:
            argv.extend(["--thinking", thinking])
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

    def _context_window(self) -> int | None:
        # opencode addresses models as "provider/model"; strip the
        # provider prefix so MODEL_REGISTRY lookups land on the real id.
        bare = self._model.split("/", 1)[-1] if "/" in self._model else self._model
        info = get_model_info(bare)
        if info is None or not info.context_window:
            return None
        return info.context_window

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

        # Stage the sandbox preamble in AGENTS.md before the CLI spawns;
        # opencode picks it up automatically from the workdir.
        _write_sandbox_agents_md(workdir)

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
            # Sensitivity-axis fields (additive, all optional). opencode
            # CLI exposes no temperature / top-p / max-output knobs on
            # the CLI itself (everything defaults to backend defaults),
            # so we leave sampling fields None.
            "sampling": {
                "temperature": None,
                "top_p": None,
                "top_k": None,
                "max_output_tokens": None,
                "stream": True,
            },
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

        # Isolation barrier — see _isolation.py. Preserve real HOME so
        # opencode's per-provider login state under ~/.config/opencode/
        # stays reachable. Env whitelist strips secret env vars
        # (OBSIDIAN_/workplace SaaS tokens/etc).
        #
        # KNOWN LIMITATION: opencode CLI as of v1.x exposes no flag to
        # suppress its user-level config (no --no-config, no
        # --strict-config). The AGENTS.md staged in workdir REPLACES the
        # default agent prompt only inside the cwd-scoped session; user
        # extensions / skills under ~/.config/opencode/skills/ may still
        # load. Filed as a known surface; track for opencode v2.
        self._isolated_env = IsolatedEnv.build(
            env_overrides=self._env_overrides,
            use_fake_home=False,
        )

        argv = self._build_argv(workdir=workdir)
        # Append the prompt as the trailing positional. opencode reads
        # the prompt as a positional argument; there is no documented
        # stdin sentinel as of v0.x.
        argv.append(prompt)

        # Spawn defensively: if the binary is missing, write a clean
        # run_end with status=unrunnable rather than crashing.
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
            self._write_run_end(
                trajectory_writer,
                status=RunStatus.unrunnable.value,
                totals_tokens_in=0,
                totals_tokens_out=0,
                totals_latency_ms=0,
                totals_cost=0.0,
            )
            return RunStatus.unrunnable
        except OSError:
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

        # opencode reads the prompt from argv; close stdin so the
        # process doesn't block waiting for input.
        if self._proc.stdin is not None:
            with contextlib.suppress(OSError):
                self._proc.stdin.close()

        idx = 0
        last_event_ts = time.monotonic()
        totals_tokens_in = 0
        totals_tokens_out = 0
        totals_latency_ms = 0
        terminal_status: str | None = None
        run_end_written = False

        # Streaming assistant turn under construction. opencode's exact
        # event shapes are not stable yet, so we accept a small zoo of
        # text/tool-call/tool-result shapes and flush a single assistant
        # turn at sensible boundaries (tool_result arrives, run finishes).
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

        def _flush_buffered() -> None:
            nonlocal buffered_assistant, idx
            if buffered_assistant is None:
                return
            trajectory_writer.write_turn(_scrub_turn(buffered_assistant, workdir_abs))
            idx += 1
            buffered_assistant = None

        def _extract_text(event: dict[str, Any]) -> str:
            # Try a few shapes opencode plausibly emits. None are
            # contractual — opencode hasn't committed to a schema yet.
            for key in ("text", "content", "delta", "message"):
                val = event.get(key)
                if isinstance(val, str) and val:
                    return val
                if isinstance(val, dict):
                    for sub in ("text", "content"):
                        inner = val.get(sub)
                        if isinstance(inner, str) and inner:
                            return inner
            return ""

        def _extract_usage(event: dict[str, Any]) -> tuple[int, int]:
            usage = event.get("usage")
            if not isinstance(usage, dict):
                return 0, 0
            t_in = int(
                usage.get("input_tokens")
                or usage.get("prompt_tokens")
                or usage.get("tokens_in")
                or 0
            )
            t_out = int(
                usage.get("output_tokens")
                or usage.get("completion_tokens")
                or usage.get("tokens_out")
                or 0
            )
            return t_in, t_out

        try:
            assert self._proc.stdout is not None
            for raw_line in self._proc.stdout:
                line = raw_line.strip()
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Non-JSON output (banner, warning, partial line);
                    # drop defensively, the schema isn't stable yet.
                    continue
                if not isinstance(event, dict):
                    continue

                etype = (
                    event.get("type")
                    or event.get("event")
                    or event.get("kind")
                    or ""
                )
                now = time.monotonic()
                latency_ms = int((now - last_event_ts) * 1000)
                last_event_ts = now

                # Assistant text — buffered until the next tool_result or
                # stream end so we don't emit a turn per token.
                if etype in {"message", "text", "assistant", "delta", "content"}:
                    role = event.get("role")
                    if role and role != "assistant":
                        # echo of our own prompt; skip
                        continue
                    text = _extract_text(event)
                    if text:
                        turn = _ensure_assistant_turn()
                        turn["model_output"] += text
                        turn["latency_ms"] += latency_ms
                    # Some opencode shapes attach usage to message events
                    t_in, t_out = _extract_usage(event)
                    totals_tokens_in += t_in
                    totals_tokens_out += t_out
                    continue

                # Tool call — attach to the in-flight assistant turn.
                if etype in {"tool_use", "tool_call", "tool"}:
                    turn = _ensure_assistant_turn()
                    turn["tool_calls"].append(
                        {
                            "id": event.get("id")
                            or event.get("tool_id")
                            or event.get("tool_use_id")
                            or f"call-{len(turn['tool_calls'])}",
                            "name": (
                                event.get("name")
                                or event.get("tool")
                                or event.get("tool_name")
                                or "tool"
                            ),
                            "args": (
                                event.get("input")
                                or event.get("arguments")
                                or event.get("parameters")
                                or event.get("args")
                                or {}
                            ),
                        }
                    )
                    turn["latency_ms"] += latency_ms
                    continue

                # Tool result — flush the assistant turn first so the
                # tool turn arrives strictly after its triggering call
                # (trajectory invariant: assistant carries tool_calls,
                # next tool turn carries tool_returns).
                if etype in {"tool_result", "tool_output", "tool_return"}:
                    _flush_buffered()
                    is_error = bool(
                        event.get("is_error")
                        or event.get("error")
                        or event.get("status") == "error"
                    )
                    detail_src = (
                        event.get("output")
                        or event.get("content")
                        or event.get("result")
                        or event.get("detail")
                        or ""
                    )
                    if isinstance(detail_src, (dict, list)):
                        detail = json.dumps(detail_src, ensure_ascii=False)
                    else:
                        detail = str(detail_src or "")
                    tool_turn = {
                        "idx": idx,
                        "role": "tool",
                        "prompt_delta": None,
                        "tool_calls": [],
                        "tool_returns": [
                            {
                                "tool_use_id": (
                                    event.get("tool_use_id")
                                    or event.get("tool_id")
                                    or event.get("id")
                                    or ""
                                ),
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

                # Terminal events.
                if etype in {"result", "done", "complete", "completed", "finish"}:
                    t_in, t_out = _extract_usage(event)
                    totals_tokens_in += t_in
                    totals_tokens_out += t_out
                    status_field = event.get("status") or event.get("result")
                    terminal_status = "error" if status_field == "error" else "completed"
                    break

                if etype in {"error", "failed"}:
                    msg = event.get("message") or event.get("error") or ""
                    if msg:
                        turn = _ensure_assistant_turn()
                        sep = "\n" if turn["model_output"] else ""
                        turn["model_output"] += f"{sep}[opencode error] {msg}"
                    terminal_status = "error"
                    continue

                # Unknown event type → drop silently. opencode's schema
                # isn't stable yet; surfacing every unknown shape would
                # spam stderr.
                continue

            self._proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            _flush_buffered()
            self.cleanup()
            status = RunStatus.timeout
            self._write_run_end(
                trajectory_writer,
                status=status.value,
                totals_tokens_in=totals_tokens_in,
                totals_tokens_out=totals_tokens_out,
                totals_latency_ms=totals_latency_ms,
                totals_cost=estimate_cost_usd(
                    self._model.split("/", 1)[-1],
                    totals_tokens_in,
                    totals_tokens_out,
                ),
            )
            run_end_written = True
            return status
        except Exception:
            with contextlib.suppress(Exception):
                _flush_buffered()
            with contextlib.suppress(Exception):
                self._write_run_end(
                    trajectory_writer,
                    status=RunStatus.error.value,
                    totals_tokens_in=totals_tokens_in,
                    totals_tokens_out=totals_tokens_out,
                    totals_latency_ms=totals_latency_ms,
                    totals_cost=estimate_cost_usd(
                        self._model.split("/", 1)[-1],
                        totals_tokens_in,
                        totals_tokens_out,
                    ),
                )
            run_end_written = True
            raise

        # Stream ended (normally or via terminal event).
        after_snapshot = snapshot(workdir)
        vault_diff = diff(before_snapshot, after_snapshot)

        if buffered_assistant is not None:
            if any(vault_diff.values()):
                buffered_assistant["vault_state_diff"] = vault_diff
            _flush_buffered()
        elif any(vault_diff.values()) and idx > 0:
            # No buffered turn but files changed — emit a minimal
            # trailing assistant turn carrying the diff so scorers see it.
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

        totals_cost = 0.0
        if totals_tokens_in > 0 or totals_tokens_out > 0:
            # Backfill cost via the pricing table; opencode under
            # provider-routed auth often emits no cost line. Strip the
            # provider/ prefix so pricing lookups land.
            bare_model = self._model.split("/", 1)[-1] if "/" in self._model else self._model
            totals_cost = estimate_cost_usd(bare_model, totals_tokens_in, totals_tokens_out)

        # Decide terminal status.
        if terminal_status == "completed":
            status = RunStatus.completed
        elif terminal_status == "error":
            status = RunStatus.error
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
