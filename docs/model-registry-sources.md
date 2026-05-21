# Model registry sources

Last refresh: **2026-05-21**. Refresh quarterly; vendors retire model IDs
faster than that and prices shift on a similar cadence.

The registry in `packages/ab-harness/ab_harness/models.py` was populated
from four parallel research agents that hit official vendor pricing +
model pages. Training data was explicitly NOT used — vendor pages are
the source of truth.

## Anthropic Claude

- <https://platform.claude.com/docs/en/docs/about-claude/models/overview>
- <https://claude.com/pricing>

Models verified: `claude-opus-4-7`, `claude-opus-4-6`, `claude-sonnet-4-7`,
`claude-sonnet-4-6`, `claude-sonnet-4-5`, `claude-haiku-4-5`.

Quirks:

- `claude-opus-4-7` uses a new tokenizer (~35% more tokens for the same
  text). Factor that into context-window math.
- `claude-sonnet-4-6` and newer carry 1M context; 4.5 stays at 200k.
- Claude Code defaults to `claude-opus-4-7`.

## OpenAI

- <https://developers.openai.com/api/docs/pricing>
- <https://developers.openai.com/api/docs/models/gpt-5.5>
- <https://developers.openai.com/api/docs/models/gpt-5.4>
- <https://developers.openai.com/api/docs/models/gpt-5.4-mini>
- <https://developers.openai.com/api/docs/models/gpt-5.4-nano>
- <https://developers.openai.com/api/docs/models/gpt-5>
- <https://developers.openai.com/api/docs/models/gpt-5-mini>
- <https://developers.openai.com/api/docs/models/gpt-5.3-codex>
- <https://developers.openai.com/api/docs/models/o3>
- <https://developers.openai.com/api/docs/models/o4-mini>
- <https://developers.openai.com/codex/models>

Quirks:

- `gpt-5.5` > 272K input → 2x input / 1.5x output surcharge. Mid-context
  benchmarks should stay below this.
- `gpt-5.3-codex` powers the Codex CLI.
- Omitted: `gpt-5.5-pro`, `gpt-5.4-pro` ($30/$180 — separate product
  class), `o3-deep-research`, `o4-mini-deep-research` (batch-only).

## Google Gemini

- <https://ai.google.dev/gemini-api/docs/pricing>

Quirks:

- Preview models (`gemini-3.1-pro-preview`,
  `gemini-3.1-flash-lite-preview`) listed because they're paid-tier
  callable today. Treat as preview-tier stability.
- `gemini-3-pro` / `gemini-3-flash` aliases resolve to the matching
  preview entries.
- `>200K` input on `gemini-3.1-pro-preview`: $4/$18 (vs $2/$12 standard).
- `>200K` input on `gemini-2.5-pro`: $2.50/$15.

## DeepSeek

- <https://api-docs.deepseek.com/quick_start/pricing>

Quirks:

- DeepSeek renamed API surface to `deepseek-v4-flash` / `deepseek-v4-pro`.
  Legacy `deepseek-chat` / `deepseek-reasoner` IDs still resolve but
  are deprecated; not in the registry.
- `deepseek-v4-pro` is at 75% off through 2026-05-31. Full price
  ~$6.96/$13.92.
- Anthropic-compat endpoint: `https://api.deepseek.com/anthropic`.

## Zhipu GLM

- <https://artificialanalysis.ai/models/glm-4-6-reasoning>
  (Zhipu's pricing page is JS-rendered and unscriptable; AA mirror is the
  closest stable reference; treat prices as ±10%.)
- <https://github.com/AndyMik90/Auto-Claude/issues/1450>
  (confirms `open.bigmodel.cn/api/anthropic` + intl mirror
  `api.z.ai/api/anthropic`)

## Moonshot Kimi

- <https://platform.kimi.ai/docs/api/overview>

Quirks:

- Anthropic-compat at `https://api.moonshot.ai/anthropic`.
- `kimi-k2.6` is current flagship; multimodal.

## Alibaba Qwen (hosted)

- <https://www.alibabacloud.com/help/en/model-studio/model-pricing>

Quirks:

- DashScope exposes OpenAI-compat only — NO Anthropic-compat proxy.
- Pricing tiered by input length on `qwen3-max` (>32K input bumps price).
- Qwen3-Coder and QwQ also ship as Apache-2.0 open weights — see local
  entries (`qwen3-coder-30b-a3b`, `qwq-plus`).

## MiniMax

- <https://platform.minimax.io/docs/api-reference/text-anthropic-api>
- <https://artificialanalysis.ai/models/minimax-m2-5>

Quirks:

- Vendor's Anthropic-compat doc lists M2, M2.1, M2.5, M2.7 (each with
  a `-highspeed` variant). Pricing reflects standard tier USD.
- Anthropic-compat at `https://api.minimax.io/anthropic`.

## Local — open weights

Each entry lists `ollama_tag` (where available) and `hf_repo`. Sources:

### Google Gemma 3

- <https://ollama.com/library/gemma3> + tags page
- <https://huggingface.co/google/gemma-3-27b-it> etc.

### Meta Llama (3.3 / 4)

- <https://ai.meta.com/blog/llama-4-multimodal-intelligence/>
- <https://huggingface.co/meta-llama/Llama-3.3-70B-Instruct>
- <https://huggingface.co/meta-llama/Llama-4-Scout-17B-16E>

Llama 4 Scout: 10M context (highest in the registry).

### Alibaba Qwen3 (open weights)

- <https://qwenlm.github.io/blog/qwen3/>
- <https://arxiv.org/pdf/2505.09388>
- <https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507>
- <https://ollama.com/library/qwen3-coder>

Tool-calling quirk: Qwen3 tool-call parsing in Ollama is flaky
(<https://github.com/ollama/ollama/issues/14601>). Prefer vLLM for
agent-grade benchmarks; Ollama is fine for completion-only tasks.

### DeepSeek (distills + V3.1)

- <https://huggingface.co/deepseek-ai/DeepSeek-R1>
- <https://huggingface.co/deepseek-ai/DeepSeek-R1-Distill-Qwen-32B>
- <https://docs.unsloth.ai/basics/deepseek-r1-0528-how-to-run-locally>
- <https://unsloth.ai/blog/deepseek-v3.1>

### Nous Research Hermes 4

- <https://huggingface.co/NousResearch/Hermes-4-70B>
- <https://huggingface.co/NousResearch/Hermes-4-405B>
- <https://huggingface.co/NousResearch/Hermes-4-14B>

### Microsoft Phi-4

- <https://huggingface.co/microsoft/phi-4>
- <https://huggingface.co/microsoft/Phi-4-reasoning>
- <https://huggingface.co/microsoft/Phi-4-mini-reasoning>
- <https://venturebeat.com/ai/microsoft-makes-powerful-phi-4-model-fully-open-source-on-hugging-face>

## Scaffolds (runners)

- claude-code: <https://code.claude.com/docs/en/headless>
- codex-cli: <https://developers.openai.com/codex/cli/reference> ·
  <https://developers.openai.com/codex/noninteractive>
- gemini-cli: <https://google-gemini.github.io/gemini-cli/docs/cli/headless.html>
- opencode: <https://opencode.ai/docs/cli/>
- pi-agent (community): <https://pi.dev/>
- hermes-agent: <https://hermes-agent.nousresearch.com/docs/>
- nanobot (Obot Platform): <https://github.com/obot-platform/nanobot>
- cursor: <https://cursor.com/docs/cli/headless>

v1 priority scaffolds: `claude-code`, `codex-cli`, `gemini-cli`, `opencode`.

Deferred for v1 (reasons in `models.PRIORITY_SCAFFOLDS_V1` /
`models.DEFERRED_SCAFFOLDS`):

- `pi-agent` — naming collision with Inflection Pi (their product has
  no first-party CLI; this is the community `earendil-works/pi`).
- `hermes-agent` — self-improving loop; needs isolation harness for
  deterministic benches.
- `nanobot` — primary mode is long-running MCP host server; one-shot
  headless is brittle.
- `cursor` — closed-source binary; opaque routing + attribution.

## Tooling notes for local hosting

- **vLLM**: best tool-calling reliability in 2026 across Llama 3.x/4,
  Hermes 4, Qwen3 (dense + MoE). FP8 weights supported. Production
  pick.
- **llama.cpp**: close second; tool-call templates work for Qwen3-Coder,
  Hermes, Llama. Apple Silicon + CPU rigs.
- **Ollama**: easiest to install, GUI-friendly via LM Studio. Qwen3
  tool-call parsing flaky (open Ollama issues #11662, #14601, #14493).
  Fine for completion-only benches.
- **LM Studio**: good GUI; tool-calling trails vLLM/llama.cpp.

Homelab on-ramp: Ollama OR LM Studio. Production: vLLM.
