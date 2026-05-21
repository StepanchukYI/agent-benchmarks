---
name: New model adapter
about: Propose a new runner for a model or agent harness
title: "[adapter] "
labels: ["adapter", "needs-triage"]
assignees: []
---

## Model

- Name:
- Version / model ID:
- Vendor:

## Harness

- [ ] CLI tool (e.g., claude-code, codex-cli, gemini-cli)
- [ ] HTTP API (e.g., direct Anthropic / OpenAI / Google / GLM / MiniMax)
- [ ] Other (describe)

## MCP support

- [ ] Native MCP client (list servers tested)
- [ ] Requires shim (see `ab_harness/runners/_shim.py`)
- [ ] No MCP support — task selection will skip L2+ that require MCPs

## Trajectory normalization plan

How will tool calls, tool returns, and per-turn token counts map onto the shared trajectory protocol (`docs/trajectory-protocol.md`)?

- Tool calls source:
- Tool returns source:
- Token accounting source:
- Latency source:
- Cost computation:
- Vault state diff capture:

## Recorded fixtures

Recorded HTTP / CLI fixtures the adapter tests will replay (no live API in CI).

- [ ] success path
- [ ] tool call + tool return
- [ ] error / timeout
- [ ] rate-limit / retry

## Open questions

Anything that needs maintainer decision before implementation.
