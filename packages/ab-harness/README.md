# ab-harness

Harness primitives for agent-benchmarks: runners, scorers, sandbox, and the trajectory protocol.

Built on [Inspect AI](https://inspect.ai-safety-institute.org.uk/) per ADR-001.

## Subsystems

- `trajectory/` — append-only JSONL writer/reader and invariant validator (build spec §6).
- `runners/` — adapters for Claude Code CLI, Codex CLI, Gemini CLI, GLM API, MiniMax API (build spec §2).
- `scorers/` — deterministic, llm-judge, state-diff, privacy-check scorers.
- `solvers/` — task orchestration glue.
- `sandbox/` — Docker materialization of config tiers (build spec §7, ADR-008).
- `reporting/` — markdown render of a finished trajectory.

See `docs/trajectory-protocol.md` and `docs/config-tiers.md` for the contracts this package implements.
