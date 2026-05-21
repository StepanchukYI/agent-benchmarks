"""Model registry — verified vendor data for the benchmark grid.

VERIFIED 2026-05-21 via four parallel research agents hitting official
vendor pricing + model pages. Sources logged in
``docs/model-registry-sources.md`` (companion file).

A model is a (vendor, weights, version) triple addressed by a stable ``id``.
Each entry declares:

* ``family`` — vendor family ("claude" | "gpt" | "codex" | "o-series" |
  "gemini" | "deepseek" | "glm" | "kimi" | "qwen" | "minimax" | "gemma" |
  "llama" | "hermes" | "phi"). Used for grouping in the leaderboard.
* ``api_compat`` — wire protocol the model speaks at its native endpoint:
  ``"anthropic"`` (Claude, MiniMax-native), ``"openai"`` (everything that
  speaks /v1/chat/completions), ``"gemini"`` (Google native).
* ``anthropic_compat_base_url`` — alternative Anthropic-compat endpoint
  if the vendor exposes one. Set for DeepSeek, GLM (Zhipu), Kimi, MiniMax.
  Null for vendors with no compat layer (Qwen DashScope).
* ``input_usd_per_1m`` / ``output_usd_per_1m`` — USD per 1M tokens.
  Locally-hosted models default to 0.
* ``compatible_runners`` — which BaseRunner adapters can drive this model.
* ``local`` — True if self-hosted (Gemma, Llama, Phi, distills).
* ``context_window``, ``supports_tools``, ``supports_vision``,
  ``param_count_b`` (local), ``ollama_tag`` (local), ``hf_repo`` (local).

Maintenance: re-run research agents quarterly; vendors retire IDs.
Add new entries here; do NOT seed from training data — it's stale.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelInfo:
    """One model entry. Immutable so it can be safely shared."""

    id: str
    family: str
    api_compat: str  # "anthropic" | "openai" | "gemini"
    input_usd_per_1m: float
    output_usd_per_1m: float
    compatible_runners: tuple[str, ...] = ()
    context_window: int = 0
    supports_tools: bool = True
    supports_vision: bool = False
    local: bool = False
    param_count_b: float = 0.0
    ollama_tag: str | None = None
    hf_repo: str | None = None
    anthropic_compat_base_url: str | None = None
    released: str = ""  # YYYY-MM
    notes: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


# Each Chinese vendor's Anthropic-compat endpoint. Operators override per
# run via env / kwargs.
VENDOR_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com",
    "zhipu": "https://open.bigmodel.cn/api/anthropic",
    "z-ai": "https://api.z.ai/api/anthropic",  # GLM intl mirror
    "moonshot": "https://api.moonshot.ai/anthropic",
    "minimax": "https://api.minimax.io/anthropic",
    "deepseek": "https://api.deepseek.com/anthropic",
}


# Local-runner OpenAI-compat base URLs. Self-hosted scaffolds expose
# OpenAI-compat APIs; the operator sets one of these per deployment.
LOCAL_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "vllm": "http://localhost:8000/v1",
    "llamacpp": "http://localhost:8080/v1",
    "textgen-webui": "http://localhost:5000/v1",
}


# v1 scaffold priorities. claude-code / codex-cli / gemini-cli / opencode
# all have documented headless modes with parseable JSON output. The
# rest are deferred until isolation + naming-collision concerns resolve.
PRIORITY_SCAFFOLDS_V1: tuple[str, ...] = (
    "claude-code", "codex-cli", "gemini-cli", "opencode", "pi-agent",
)
DEFERRED_SCAFFOLDS: tuple[str, ...] = (
    "hermes-agent",   # self-improving loop — determinism risk for benches
    "nanobot",        # MCP-host first, single-shot headless is brittle
    "cursor",         # closed-source router, opaque attribution
)


_C = "claude-code"
_O = "opencode"
_H = "hermes-agent"
_P = "pi-agent"
_N = "nanobot"
_CU = "cursor"
_CX = "codex-cli"
_G = "gemini-cli"
_A = "anthropic-compat"
_OA = "openai-compat"
_L = "local"


MODEL_REGISTRY: tuple[ModelInfo, ...] = (
    # ──────────────────────────────────────────────────────────────────
    # Anthropic Claude
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="claude-opus-4-7",
        family="claude",
        api_compat="anthropic",
        input_usd_per_1m=5.00,
        output_usd_per_1m=25.00,
        compatible_runners=(_C, _O, _H, _P, _N, _CU, _A),
        context_window=1_000_000,
        supports_vision=True,
        released="2026-04",
        notes="Flagship; adaptive thinking; new tokenizer (may use ~35% more tokens for same text); Claude Code default; 128k max output.",
    ),
    ModelInfo(
        id="claude-opus-4-6",
        family="claude",
        api_compat="anthropic",
        input_usd_per_1m=5.00,
        output_usd_per_1m=25.00,
        compatible_runners=(_C, _O, _H, _A),
        context_window=1_000_000,
        supports_vision=True,
        released="2025-11",
        notes="Previous-gen Opus; useful baseline against 4.7.",
    ),
    ModelInfo(
        id="claude-sonnet-4-7",
        family="claude",
        api_compat="anthropic",
        input_usd_per_1m=3.00,
        output_usd_per_1m=15.00,
        compatible_runners=(_C, _O, _H, _P, _N, _CU, _A),
        context_window=1_000_000,
        supports_vision=True,
        released="2026-04",
    ),
    ModelInfo(
        id="claude-sonnet-4-6",
        family="claude",
        api_compat="anthropic",
        input_usd_per_1m=3.00,
        output_usd_per_1m=15.00,
        compatible_runners=(_C, _O, _H, _P, _N, _CU, _A),
        context_window=1_000_000,
        supports_vision=True,
        released="2026-01",
        notes="Speed/intelligence tradeoff sweet spot; 64k max output.",
    ),
    ModelInfo(
        id="claude-sonnet-4-5",
        family="claude",
        api_compat="anthropic",
        input_usd_per_1m=3.00,
        output_usd_per_1m=15.00,
        compatible_runners=(_C, _O, _H, _A),
        context_window=200_000,
        supports_vision=True,
        released="2025-09",
        notes="Legacy but callable; 200k context (vs 1M on 4.6/4.7).",
    ),
    ModelInfo(
        id="claude-haiku-4-5",
        family="claude",
        api_compat="anthropic",
        input_usd_per_1m=1.00,
        output_usd_per_1m=5.00,
        compatible_runners=(_C, _O, _H, _A),
        context_window=200_000,
        supports_vision=True,
        released="2025-10",
        notes="Cheap near-frontier; default LLM-judge model.",
    ),

    # ──────────────────────────────────────────────────────────────────
    # OpenAI GPT / Codex / o-series
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="gpt-5.5",
        family="gpt",
        api_compat="openai",
        input_usd_per_1m=5.00,
        output_usd_per_1m=30.00,
        compatible_runners=(_CX, _O, _P, _N, _CU, _OA),
        context_window=1_050_000,
        supports_vision=True,
        released="2026-04",
        notes="Current OpenAI frontier; >272k input triggers 2x/1.5x surcharge.",
    ),
    ModelInfo(
        id="gpt-5.4",
        family="gpt",
        api_compat="openai",
        input_usd_per_1m=2.50,
        output_usd_per_1m=15.00,
        compatible_runners=(_CX, _O, _P, _N, _CU, _OA),
        context_window=1_050_000,
        supports_vision=True,
        released="2026-03",
    ),
    ModelInfo(
        id="gpt-5.4-mini",
        family="gpt",
        api_compat="openai",
        input_usd_per_1m=0.75,
        output_usd_per_1m=4.50,
        compatible_runners=(_CX, _O, _P, _N, _CU, _OA),
        context_window=400_000,
        supports_vision=True,
        released="2026-03",
    ),
    ModelInfo(
        id="gpt-5.4-nano",
        family="gpt",
        api_compat="openai",
        input_usd_per_1m=0.20,
        output_usd_per_1m=1.25,
        compatible_runners=(_CX, _O, _OA),
        context_window=400_000,
        supports_vision=True,
        released="2026-03",
        notes="Cheapest current OpenAI; classification / extraction / subagent role.",
    ),
    ModelInfo(
        id="gpt-5",
        family="gpt",
        api_compat="openai",
        input_usd_per_1m=1.25,
        output_usd_per_1m=10.00,
        compatible_runners=(_CX, _O, _P, _N, _CU, _OA),
        context_window=400_000,
        supports_vision=True,
        released="2025-08",
    ),
    ModelInfo(
        id="gpt-5-mini",
        family="gpt",
        api_compat="openai",
        input_usd_per_1m=0.25,
        output_usd_per_1m=2.00,
        compatible_runners=(_CX, _O, _OA),
        context_window=400_000,
        supports_vision=True,
        released="2025-08",
    ),
    ModelInfo(
        id="gpt-5.3-codex",
        family="codex",
        api_compat="openai",
        input_usd_per_1m=1.75,
        output_usd_per_1m=14.00,
        compatible_runners=(_CX, _O, _OA),
        context_window=400_000,
        supports_vision=True,
        released="2026-02",
        notes="Powers Codex CLI; agentic coding model; reasoning low/medium/high/xhigh.",
    ),
    ModelInfo(
        id="o3",
        family="o-series",
        api_compat="openai",
        input_usd_per_1m=2.00,
        output_usd_per_1m=8.00,
        compatible_runners=(_CX, _O, _OA),
        context_window=200_000,
        supports_vision=True,
        released="2025-04",
    ),
    ModelInfo(
        id="o4-mini",
        family="o-series",
        api_compat="openai",
        input_usd_per_1m=1.10,
        output_usd_per_1m=4.40,
        compatible_runners=(_CX, _O, _OA),
        context_window=200_000,
        supports_vision=True,
        released="2025-04",
    ),

    # ──────────────────────────────────────────────────────────────────
    # Google Gemini
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="gemini-3.1-pro-preview",
        family="gemini",
        api_compat="gemini",
        input_usd_per_1m=2.00,
        output_usd_per_1m=12.00,
        compatible_runners=(_G, _O, _P, _N, _CU),
        context_window=1_048_576,
        supports_vision=True,
        released="2026-04",
        notes="Standard tier (<=200K). Beyond 200K: $4/$18.",
        aliases=("gemini-3-pro",),
    ),
    ModelInfo(
        id="gemini-3.5-flash",
        family="gemini",
        api_compat="gemini",
        input_usd_per_1m=1.50,
        output_usd_per_1m=9.00,
        compatible_runners=(_G, _O, _P, _N, _CU),
        context_window=1_048_576,
        supports_vision=True,
        released="2026-05",
        notes="Newest fast-tier flagship; thinking model.",
        aliases=("gemini-3-flash",),
    ),
    ModelInfo(
        id="gemini-3.1-flash-lite-preview",
        family="gemini",
        api_compat="gemini",
        input_usd_per_1m=0.25,
        output_usd_per_1m=1.50,
        compatible_runners=(_G, _O, _OA),
        context_window=1_048_576,
        supports_vision=True,
        released="2026-03",
    ),
    ModelInfo(
        id="gemini-2.5-pro",
        family="gemini",
        api_compat="gemini",
        input_usd_per_1m=1.25,
        output_usd_per_1m=10.00,
        compatible_runners=(_G, _O, _CU),
        context_window=1_048_576,
        supports_vision=True,
        released="2025-09",
        notes=">200K tier: $2.50/$15.",
    ),
    ModelInfo(
        id="gemini-2.5-flash",
        family="gemini",
        api_compat="gemini",
        input_usd_per_1m=0.30,
        output_usd_per_1m=2.50,
        compatible_runners=(_G, _O),
        context_window=1_048_576,
        supports_vision=True,
        released="2025-09",
    ),
    ModelInfo(
        id="gemini-2.5-flash-lite",
        family="gemini",
        api_compat="gemini",
        input_usd_per_1m=0.10,
        output_usd_per_1m=0.40,
        compatible_runners=(_G, _O),
        context_window=1_048_576,
        supports_vision=True,
        released="2025-09",
    ),

    # ──────────────────────────────────────────────────────────────────
    # DeepSeek (hosted)
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="deepseek-v4-flash",
        family="deepseek",
        api_compat="openai",
        input_usd_per_1m=0.14,
        output_usd_per_1m=0.28,
        compatible_runners=(_O, _A, _OA),
        context_window=1_000_000,
        anthropic_compat_base_url="https://api.deepseek.com/anthropic",
        released="2026-04",
        notes="Replaces deepseek-chat/reasoner; thinking + non-thinking modes; cache-hit input $0.014.",
    ),
    ModelInfo(
        id="deepseek-v4-pro",
        family="deepseek",
        api_compat="openai",
        input_usd_per_1m=1.74,
        output_usd_per_1m=3.48,
        compatible_runners=(_O, _A, _OA),
        context_window=1_000_000,
        anthropic_compat_base_url="https://api.deepseek.com/anthropic",
        released="2026-04",
        notes="75% off through 2026-05-31; full ~$6.96/$13.92.",
    ),

    # ──────────────────────────────────────────────────────────────────
    # Zhipu GLM (Anthropic-compat via open.bigmodel.cn or api.z.ai)
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="glm-4.6",
        family="glm",
        api_compat="openai",
        input_usd_per_1m=0.43,
        output_usd_per_1m=1.74,
        compatible_runners=(_O, _A, _OA),
        context_window=202_752,
        anthropic_compat_base_url="https://open.bigmodel.cn/api/anthropic",
        released="2025-10",
        notes="Primary GLM coder; intl mirror https://api.z.ai/api/anthropic.",
    ),
    ModelInfo(
        id="glm-4.5",
        family="glm",
        api_compat="openai",
        input_usd_per_1m=0.60,
        output_usd_per_1m=2.20,
        compatible_runners=(_O, _A, _OA),
        context_window=131_072,
        anthropic_compat_base_url="https://open.bigmodel.cn/api/anthropic",
        released="2025-07",
    ),
    ModelInfo(
        id="glm-4.5v",
        family="glm",
        api_compat="openai",
        input_usd_per_1m=0.60,
        output_usd_per_1m=1.80,
        compatible_runners=(_O, _A, _OA),
        context_window=65_536,
        supports_vision=True,
        anthropic_compat_base_url="https://open.bigmodel.cn/api/anthropic",
        released="2025-08",
    ),

    # ──────────────────────────────────────────────────────────────────
    # Moonshot Kimi
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="kimi-k2.6",
        family="kimi",
        api_compat="openai",
        input_usd_per_1m=0.60,
        output_usd_per_1m=2.50,
        compatible_runners=(_O, _A, _OA),
        context_window=262_144,
        supports_vision=True,
        anthropic_compat_base_url="https://api.moonshot.ai/anthropic",
        released="2026-04",
        notes="Current Kimi flagship; multimodal vision+text.",
    ),
    ModelInfo(
        id="kimi-k2-thinking",
        family="kimi",
        api_compat="openai",
        input_usd_per_1m=0.60,
        output_usd_per_1m=2.40,
        compatible_runners=(_O, _A, _OA),
        context_window=262_144,
        anthropic_compat_base_url="https://api.moonshot.ai/anthropic",
        released="2025-11",
    ),
    ModelInfo(
        id="kimi-k2-0905-preview",
        family="kimi",
        api_compat="openai",
        input_usd_per_1m=0.15,
        output_usd_per_1m=2.50,
        compatible_runners=(_O, _A, _OA),
        context_window=262_144,
        anthropic_compat_base_url="https://api.moonshot.ai/anthropic",
        released="2025-09",
        notes="K2 base MoE; cheapest Kimi tier.",
    ),

    # ──────────────────────────────────────────────────────────────────
    # Alibaba Qwen (hosted; DashScope OpenAI-compat, NO Anthropic compat)
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="qwen3-max",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.359,
        output_usd_per_1m=1.434,
        compatible_runners=(_O, _OA),
        context_window=262_144,
        supports_vision=True,
        released="2025-09",
        notes="Hosted DashScope; tiered pricing — >32K input bumps price.",
    ),
    ModelInfo(
        id="qwen3-coder-plus",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.574,
        output_usd_per_1m=2.294,
        compatible_runners=(_O, _OA),
        context_window=1_048_576,
        released="2025-10",
        notes="Coder-tuned; open-weights variant also available (qwen3-coder-30b-a3b / 480b).",
    ),
    ModelInfo(
        id="qwen-plus",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.115,
        output_usd_per_1m=0.287,
        compatible_runners=(_O, _OA),
        context_window=1_048_576,
        released="2025-12",
    ),
    ModelInfo(
        id="qwen3-vl-plus",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.143,
        output_usd_per_1m=1.434,
        compatible_runners=(_O, _OA),
        context_window=262_144,
        supports_vision=True,
        released="2025-11",
    ),
    ModelInfo(
        id="qwq-plus",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.230,
        output_usd_per_1m=0.574,
        compatible_runners=(_O, _OA),
        context_window=131_072,
        released="2025-08",
        notes="QwQ reasoning model; hosted + open-weights.",
    ),

    # ──────────────────────────────────────────────────────────────────
    # MiniMax (native Anthropic-compat)
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="MiniMax-M2.7",
        family="minimax",
        api_compat="anthropic",
        input_usd_per_1m=0.30,
        output_usd_per_1m=1.20,
        compatible_runners=(_O, _A),
        context_window=204_800,
        anthropic_compat_base_url="https://api.minimax.io/anthropic",
        released="2026-05",
        notes="Latest in M2.x line.",
    ),
    ModelInfo(
        id="MiniMax-M2.5",
        family="minimax",
        api_compat="anthropic",
        input_usd_per_1m=0.30,
        output_usd_per_1m=1.20,
        compatible_runners=(_O, _A),
        context_window=204_800,
        anthropic_compat_base_url="https://api.minimax.io/anthropic",
        released="2026-02",
        notes="80.2% SWE-Bench. Vendor recommends Anthropic SDK path.",
    ),
    ModelInfo(
        id="MiniMax-M2.5-highspeed",
        family="minimax",
        api_compat="anthropic",
        input_usd_per_1m=0.30,
        output_usd_per_1m=2.40,
        compatible_runners=(_O, _A),
        context_window=204_800,
        anthropic_compat_base_url="https://api.minimax.io/anthropic",
        released="2026-02",
        notes="~100 tps output vs ~60 tps for standard.",
    ),
    ModelInfo(
        id="MiniMax-M2",
        family="minimax",
        api_compat="anthropic",
        input_usd_per_1m=0.26,
        output_usd_per_1m=1.00,
        compatible_runners=(_O, _A),
        context_window=204_800,
        anthropic_compat_base_url="https://api.minimax.io/anthropic",
        released="2025-10",
    ),

    # ──────────────────────────────────────────────────────────────────
    # LOCAL — Google Gemma 3 (multimodal 4B+)
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="gemma3-27b",
        family="gemma",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        supports_tools=False,
        supports_vision=True,
        local=True,
        param_count_b=27.0,
        ollama_tag="gemma3:27b",
        hf_repo="google/gemma-3-27b-it",
        released="2025-03",
        notes="Flagship Gemma 3; single 24-48GB GPU.",
    ),
    ModelInfo(
        id="gemma3-12b",
        family="gemma",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        supports_tools=False,
        supports_vision=True,
        local=True,
        param_count_b=12.0,
        ollama_tag="gemma3:12b",
        hf_repo="google/gemma-3-12b-it",
        released="2025-03",
        notes="Mid-tier multimodal; 140+ languages.",
    ),
    ModelInfo(
        id="gemma3-4b",
        family="gemma",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        supports_tools=False,
        supports_vision=True,
        local=True,
        param_count_b=4.0,
        ollama_tag="gemma3:4b",
        hf_repo="google/gemma-3-4b-it",
        released="2025-03",
        notes="Default `gemma3:latest`.",
    ),
    ModelInfo(
        id="gemma3-1b",
        family="gemma",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=32_768,
        supports_tools=False,
        local=True,
        param_count_b=1.0,
        ollama_tag="gemma3:1b",
        hf_repo="google/gemma-3-1b-it",
        released="2025-03",
    ),

    # ──────────────────────────────────────────────────────────────────
    # LOCAL — Meta Llama
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="llama-4-maverick-17b-128e",
        family="llama",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=1_048_576,
        supports_vision=True,
        local=True,
        param_count_b=400.0,
        ollama_tag="llama4:maverick",
        hf_repo="meta-llama/Llama-4-Maverick-17B-128E-Instruct",
        released="2025-04",
        notes="MoE 17B active / 400B total; 8x H100 or aggressive quant.",
    ),
    ModelInfo(
        id="llama-4-scout-17b-16e",
        family="llama",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=10_485_760,
        supports_vision=True,
        local=True,
        param_count_b=109.0,
        ollama_tag="llama4:scout",
        hf_repo="meta-llama/Llama-4-Scout-17B-16E-Instruct",
        released="2025-04",
        notes="MoE 17B active / 109B total; fits single H100; 10M context.",
    ),
    ModelInfo(
        id="llama-3.3-70b-instruct",
        family="llama",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O, _H),
        context_window=131_072,
        local=True,
        param_count_b=70.0,
        ollama_tag="llama3.3:70b",
        hf_repo="meta-llama/Llama-3.3-70B-Instruct",
        released="2024-12",
        notes="Most-deployed open 70B; near-405B quality at 70B cost.",
    ),

    # ──────────────────────────────────────────────────────────────────
    # LOCAL — Alibaba Qwen3 (open weights)
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="qwen3-coder-480b-a35b",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=262_144,
        local=True,
        param_count_b=480.0,
        ollama_tag="qwen3-coder:480b",
        hf_repo="Qwen/Qwen3-Coder-480B-A35B-Instruct",
        released="2025-07",
        notes="MoE 35B active; ~290GB; flagship open coder.",
    ),
    ModelInfo(
        id="qwen3-235b-a22b-instruct-2507",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=262_144,
        local=True,
        param_count_b=235.0,
        ollama_tag="qwen3:235b",
        hf_repo="Qwen/Qwen3-235B-A22B-Instruct-2507",
        released="2025-07",
        notes="MoE 22B active; best Apache-2.0 generalist.",
    ),
    ModelInfo(
        id="qwen3-coder-30b-a3b",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=262_144,
        local=True,
        param_count_b=30.0,
        ollama_tag="qwen3-coder:30b",
        hf_repo="Qwen/Qwen3-Coder-30B-A3B-Instruct",
        released="2025-07",
        notes="Best local coding model for homelab; 256K ctx.",
    ),
    ModelInfo(
        id="qwen3-32b",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        local=True,
        param_count_b=32.0,
        ollama_tag="qwen3:32b",
        hf_repo="Qwen/Qwen3-32B",
        released="2025-04",
        notes="Top dense Qwen3; thinking + non-thinking modes; agent-grade.",
    ),
    ModelInfo(
        id="qwen3-30b-a3b",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        local=True,
        param_count_b=30.0,
        ollama_tag="qwen3:30b",
        hf_repo="Qwen/Qwen3-30B-A3B",
        released="2025-04",
        notes="MoE 3B active; CPU+iGPU friendly.",
    ),
    ModelInfo(
        id="qwen3-14b",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        local=True,
        param_count_b=14.0,
        ollama_tag="qwen3:14b",
        hf_repo="Qwen/Qwen3-14B",
        released="2025-04",
        notes="Tool-calling reliable in vLLM/llama.cpp, intermittent in Ollama.",
    ),
    ModelInfo(
        id="qwen3-8b",
        family="qwen",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        local=True,
        param_count_b=8.0,
        ollama_tag="qwen3:8b",
        hf_repo="Qwen/Qwen3-8B",
        released="2025-04",
    ),

    # ──────────────────────────────────────────────────────────────────
    # LOCAL — DeepSeek distills + V3.1
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="deepseek-v3.1",
        family="deepseek",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        local=True,
        param_count_b=671.0,
        ollama_tag="deepseek-v3.1:671b",
        hf_repo="deepseek-ai/DeepSeek-V3.1",
        released="2025-08",
        notes="MoE 37B active; 4-bit GGUF ~400GB on multi-GPU homelab.",
    ),
    ModelInfo(
        id="deepseek-r1-distill-llama-70b",
        family="deepseek",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        supports_tools=False,
        local=True,
        param_count_b=70.0,
        ollama_tag="deepseek-r1:70b",
        hf_repo="deepseek-ai/DeepSeek-R1-Distill-Llama-70B",
        released="2025-01",
        notes="Largest R1 distill; Llama-3 base.",
    ),
    ModelInfo(
        id="deepseek-r1-distill-qwen-32b",
        family="deepseek",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        supports_tools=False,
        local=True,
        param_count_b=32.0,
        ollama_tag="deepseek-r1:32b",
        hf_repo="deepseek-ai/DeepSeek-R1-Distill-Qwen-32B",
        released="2025-01",
        notes="Beats o1-mini math/code; sweet spot for 24-48GB VRAM.",
    ),
    ModelInfo(
        id="deepseek-r1-0528-qwen3-8b",
        family="deepseek",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        supports_tools=False,
        local=True,
        param_count_b=8.0,
        ollama_tag="deepseek-r1:8b-0528-qwen3-q4_K_M",
        hf_repo="deepseek-ai/DeepSeek-R1-0528-Qwen3-8B",
        released="2025-05",
    ),
    ModelInfo(
        id="deepseek-r1-distill-qwen-7b",
        family="deepseek",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        supports_tools=False,
        local=True,
        param_count_b=7.0,
        ollama_tag="deepseek-r1:7b",
        hf_repo="deepseek-ai/DeepSeek-R1-Distill-Qwen-7B",
        released="2025-01",
    ),

    # ──────────────────────────────────────────────────────────────────
    # LOCAL — Nous Research Hermes 4
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="hermes-4-405b",
        family="hermes",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_H, _O, _L),
        context_window=131_072,
        local=True,
        param_count_b=405.0,
        hf_repo="NousResearch/Hermes-4-405B",
        released="2025-08",
        notes="Llama-3.1-405B base; FP8 weights for multi-GPU rigs.",
    ),
    ModelInfo(
        id="hermes-4-70b",
        family="hermes",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_H, _O, _L),
        context_window=131_072,
        local=True,
        param_count_b=70.0,
        hf_repo="NousResearch/Hermes-4-70B",
        released="2025-08",
        notes="Llama-3.1-70B base; strong tool use.",
    ),
    ModelInfo(
        id="hermes-4-14b",
        family="hermes",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_H, _O, _L),
        context_window=131_072,
        local=True,
        param_count_b=14.0,
        hf_repo="NousResearch/Hermes-4-14B",
        released="2025-08",
        notes="Qwen3 base; hybrid reasoning with <think> tags.",
    ),

    # ──────────────────────────────────────────────────────────────────
    # LOCAL — Microsoft Phi-4
    # ──────────────────────────────────────────────────────────────────
    ModelInfo(
        id="phi-4-reasoning",
        family="phi",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=32_768,
        supports_tools=False,
        local=True,
        param_count_b=14.0,
        ollama_tag="phi4-reasoning:14b",
        hf_repo="microsoft/Phi-4-reasoning",
        released="2025-05",
        notes="RL-trained reasoner; o1-mini class.",
    ),
    ModelInfo(
        id="phi-4-mini-reasoning",
        family="phi",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=131_072,
        supports_tools=False,
        local=True,
        param_count_b=3.8,
        ollama_tag="phi4-mini-reasoning:3.8b",
        hf_repo="microsoft/Phi-4-mini-reasoning",
        released="2025-04",
        notes="Edge reasoner for math; runs on laptops.",
    ),
    ModelInfo(
        id="phi-4",
        family="phi",
        api_compat="openai",
        input_usd_per_1m=0.0,
        output_usd_per_1m=0.0,
        compatible_runners=(_L, _O),
        context_window=16_384,
        supports_tools=False,
        local=True,
        param_count_b=14.0,
        ollama_tag="phi4:14b",
        hf_repo="microsoft/phi-4",
        released="2025-01",
        notes="Dense 14B STEM; short 16K context limits agent use.",
    ),
)


# ──────────────────────────────────────────────────────────────────────
# Lookup + filter helpers
# ──────────────────────────────────────────────────────────────────────

def list_models(*, include_local: bool = True) -> list[ModelInfo]:
    if include_local:
        return list(MODEL_REGISTRY)
    return [m for m in MODEL_REGISTRY if not m.local]


def get_model_info(model_id: str) -> ModelInfo | None:
    """Exact match, then alias match, then prefix match (longest first)."""
    if not model_id:
        return None
    for m in MODEL_REGISTRY:
        if m.id == model_id:
            return m
    for m in MODEL_REGISTRY:
        if model_id in m.aliases:
            return m
    candidates = [m for m in MODEL_REGISTRY if model_id.startswith(m.id)]
    if candidates:
        return max(candidates, key=lambda m: len(m.id))
    return None


def models_for_runner(runner_id: str) -> list[ModelInfo]:
    return [m for m in MODEL_REGISTRY if runner_id in m.compatible_runners]


def runners_for_model(model_id: str) -> list[str]:
    info = get_model_info(model_id)
    if info is None:
        return []
    return list(info.compatible_runners)


def models_by_family(family: str) -> list[ModelInfo]:
    return [m for m in MODEL_REGISTRY if m.family == family]


def vendor_base_url(vendor: str) -> str:
    """Anthropic-compat base_url for a vendor key.

    Falls back to Anthropic's URL on unknown vendors so a typo doesn't
    silently route nowhere — the API call will fail loudly on auth.
    """
    return VENDOR_BASE_URLS.get(vendor.lower(), VENDOR_BASE_URLS["anthropic"])


def local_base_url(scaffold: str) -> str:
    """OpenAI-compat base_url for a self-host scaffold."""
    return LOCAL_BASE_URLS.get(scaffold.lower(), LOCAL_BASE_URLS["ollama"])


__all__ = [
    "DEFERRED_SCAFFOLDS",
    "LOCAL_BASE_URLS",
    "MODEL_REGISTRY",
    "PRIORITY_SCAFFOLDS_V1",
    "VENDOR_BASE_URLS",
    "ModelInfo",
    "get_model_info",
    "list_models",
    "local_base_url",
    "models_by_family",
    "models_for_runner",
    "runners_for_model",
    "vendor_base_url",
]
