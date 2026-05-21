# Adding a model adapter

A "runner" wraps a model or agent harness so the rest of the system sees the same trajectory protocol. This guide describes the runner contract, how to record HTTP fixtures, and how to register the runner.

## Runner contract

Subclass `ab_harness.runners.base.BaseRunner` (Python ABC). Implement:

```python
class BaseRunner(abc.ABC):
    name: str
    harness: str

    @abc.abstractmethod
    async def materialize(self, tier: Tier, task: Task) -> SandboxHandle: ...

    @abc.abstractmethod
    async def run(self, handle: SandboxHandle, task: Task) -> AsyncIterator[TrajectoryEvent]: ...

    @abc.abstractmethod
    async def cleanup(self, handle: SandboxHandle) -> None: ...
```

Contract:

- `materialize` mounts the tier (CLAUDE.md, skills, MCP configs, vault snapshot) and prepares the sandbox. It must record the `tier_hash` so the orchestrator can emit `run_start`.
- `run` is an async generator that yields trajectory events in order: zero or more `turn` events, followed by zero or more interleaved `scorer` events if the runner produces them inline, then a terminal sentinel. The orchestrator wraps the stream with `run_start` and `run_end` and inserts any scorer chain not produced by the runner itself.
- Every yielded `turn` event MUST conform to `ab_datasets.schemas.Turn`: monotonic `idx` from 0; aligned `tool_calls` and `tool_returns` arrays; `vault_state_diff` null for stateless turns; token, latency, and cost fields populated.
- `cleanup` removes the sandbox even on cancellation or error.

If the harness has a native MCP client, configure it from the tier manifest's `mcps:` list. If it does not, route MCPs through `ab_harness.runners._shim.MCPShim` — see OQ6 in the build spec.

## Registering the runner

1. Add a module under `packages/ab-harness/ab_harness/runners/<name>.py`.
2. Register in `packages/ab-harness/ab_harness/runners/__init__.py`:
   ```python
   from .registry import register
   from .my_runner import MyRunner
   register("my-runner", MyRunner)
   ```
3. Add an entry in `docs/trust-tiers.md` describing trust-tier compatibility (can the trajectory be re-scored deterministically? if not, ceiling is `self_reported`).
4. Add a unit-test module under `packages/ab-harness/tests/runners/test_my_runner.py`.

## Recording HTTP fixtures (no live API in CI)

CI never makes live model calls. Adapter tests replay recorded HTTP fixtures.

1. Record once locally:
   ```bash
   uv run pytest packages/ab-harness/tests/runners/test_my_runner.py --record
   ```
   The harness uses an HTTP recorder (VCR-style) and writes cassettes under `packages/ab-harness/tests/runners/cassettes/`.
2. Scrub secrets from the cassette: API keys, bearer tokens, identifying user data. Run `python scripts/privacy_scan.py` against the cassettes directory.
3. Commit the scrubbed cassettes. On CI the tests replay them; `--record` is a no-op.

For CLI-based harnesses (Claude Code, Codex CLI, Gemini CLI) the recorder captures stdin/stdout transcripts under the same cassette layout. The harness invokes the binary with `--harness-fixtures <path>` to redirect actual command execution.

## Trajectory normalization

Each runner is responsible for emitting a normalized trajectory. Common pitfalls:

- Tool calls are arrays even when there is exactly one. Tool returns must be the same length and in the same order as tool calls.
- `tokens_in` is the prompt token count for that turn, not the cumulative count. `run_end.totals.tokens_in` is the cumulative sum.
- `cost_usd` is per-turn, summed in `run_end.totals.cost_usd`.
- `vault_state_diff` paths are relative to the sandbox vault root, never absolute.

See `docs/trajectory-protocol.md` for the full schema and invariants.
