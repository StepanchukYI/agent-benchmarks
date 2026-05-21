"""Token-based cost estimation for runners that don't emit cost_usd.

Prices in USD per 1M tokens. Source: Anthropic pricing page (and OpenAI/
Google equivalents for future adapters). Update when models retire or
new ones land.
"""
from __future__ import annotations

_PRICING_USD_PER_1M = {
    # Anthropic Claude (input, output)
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-opus-4-5": (15.0, 75.0),
    "claude-haiku-4-5": (1.0, 5.0),
    # Catch-all family fallbacks (matched by prefix when exact model missing)
    "claude-sonnet": (3.0, 15.0),
    "claude-opus": (15.0, 75.0),
    "claude-haiku": (1.0, 5.0),
}


def estimate_cost_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    """Estimate cost in USD from token counts.

    Falls back through prefix matches before returning 0.0 for unknown models.
    Returns 0.0 if both token counts are 0 (no-op turn).
    """
    if tokens_in <= 0 and tokens_out <= 0:
        return 0.0
    pricing = _PRICING_USD_PER_1M.get(model)
    if pricing is None:
        # Prefix match — handle versioned variants.
        for key, val in _PRICING_USD_PER_1M.items():
            if model.startswith(key):
                pricing = val
                break
    if pricing is None:
        return 0.0
    in_per_1m, out_per_1m = pricing
    return (tokens_in / 1_000_000.0) * in_per_1m + (tokens_out / 1_000_000.0) * out_per_1m
