"""Token-based cost estimation for runners that don't emit cost_usd.

Pricing per 1M tokens (USD). Mirrors the verified entries in
``ab_harness.models.MODEL_REGISTRY``; kept here as a flat dict so the
hot path doesn't import the registry. When prices shift, update BOTH.

LAST REFRESH: 2026-05-21 via the same research pass that populated the
registry. Sources logged in ``docs/model-registry-sources.md``.
"""

from __future__ import annotations

_PRICING_USD_PER_1M: dict[str, tuple[float, float]] = {
    # ── Anthropic Claude ──────────────────────────────────────────────
    "claude-opus-4-7": (5.00, 25.00),
    "claude-opus-4-6": (5.00, 25.00),
    "claude-sonnet-4-7": (3.00, 15.00),
    "claude-sonnet-4-6": (3.00, 15.00),
    "claude-sonnet-4-5": (3.00, 15.00),
    "claude-haiku-4-5": (1.00, 5.00),
    # Family prefix fallbacks (longest prefix wins inside the helper).
    "claude-opus": (5.00, 25.00),
    "claude-sonnet": (3.00, 15.00),
    "claude-haiku": (1.00, 5.00),

    # ── OpenAI ────────────────────────────────────────────────────────
    "gpt-5.5": (5.00, 30.00),
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-5.4-nano": (0.20, 1.25),
    "gpt-5.4": (2.50, 15.00),
    "gpt-5.3-codex": (1.75, 14.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "o4-mini": (1.10, 4.40),
    "o3": (2.00, 8.00),

    # ── Google Gemini ─────────────────────────────────────────────────
    "gemini-3.5-flash": (1.50, 9.00),
    "gemini-3.1-pro-preview": (2.00, 12.00),
    "gemini-3.1-flash-lite-preview": (0.25, 1.50),
    "gemini-3-pro": (2.00, 12.00),     # alias
    "gemini-3-flash": (1.50, 9.00),    # alias
    "gemini-2.5-pro": (1.25, 10.00),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),

    # ── DeepSeek ──────────────────────────────────────────────────────
    "deepseek-v4-flash": (0.14, 0.28),
    "deepseek-v4-pro": (1.74, 3.48),

    # ── Zhipu GLM ─────────────────────────────────────────────────────
    "glm-4.6": (0.43, 1.74),
    "glm-4.5v": (0.60, 1.80),
    "glm-4.5": (0.60, 2.20),

    # ── Moonshot Kimi ─────────────────────────────────────────────────
    "kimi-k2.6": (0.60, 2.50),
    "kimi-k2-thinking": (0.60, 2.40),
    "kimi-k2-0905-preview": (0.15, 2.50),

    # ── Alibaba Qwen ──────────────────────────────────────────────────
    "qwen3-max": (0.359, 1.434),
    "qwen3-coder-plus": (0.574, 2.294),
    "qwen3-vl-plus": (0.143, 1.434),
    "qwen-plus": (0.115, 0.287),
    "qwq-plus": (0.230, 0.574),

    # ── MiniMax ───────────────────────────────────────────────────────
    "MiniMax-M2.7": (0.30, 1.20),
    "MiniMax-M2.5-highspeed": (0.30, 2.40),
    "MiniMax-M2.5": (0.30, 1.20),
    "MiniMax-M2": (0.26, 1.00),
}


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate cost in USD from token counts.

    Falls back through longest-prefix match before returning 0.0 for
    unknown models. Returns 0.0 if both token counts are 0 (no-op turn).
    """
    if tokens_in <= 0 and tokens_out <= 0:
        return 0.0
    pricing = _PRICING_USD_PER_1M.get(model)
    if pricing is None:
        # Longest prefix wins so "claude-opus-4-7" doesn't get matched
        # by the shorter "claude-opus" entry.
        candidates = [k for k in _PRICING_USD_PER_1M if model.startswith(k)]
        if candidates:
            pricing = _PRICING_USD_PER_1M[max(candidates, key=len)]
    if pricing is None:
        return 0.0
    in_per_1m, out_per_1m = pricing
    return (
        (tokens_in / 1_000_000.0) * in_per_1m
        + (tokens_out / 1_000_000.0) * out_per_1m
    )
