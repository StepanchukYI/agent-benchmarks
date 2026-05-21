"""Token-based pseudo-cost estimation."""

from __future__ import annotations

import pytest
from ab_harness.pricing import estimate_cost_usd


def test_known_model_exact_match() -> None:
    # 1000 in * 3/1M + 500 out * 15/1M = 0.003 + 0.0075 = 0.0105
    cost = estimate_cost_usd("claude-sonnet-4-5", 1000, 500)
    assert cost == pytest.approx(0.0105)


def test_prefix_fallback_versioned_variant() -> None:
    # Unknown exact key; should match `claude-sonnet-4-5` by prefix.
    cost = estimate_cost_usd("claude-sonnet-4-5-20260101", 1000, 500)
    assert cost == pytest.approx(0.0105)


def test_unknown_model_returns_zero() -> None:
    assert estimate_cost_usd("gpt-9-ultra", 1000, 500) == 0.0


def test_zero_tokens_returns_zero() -> None:
    assert estimate_cost_usd("claude-sonnet-4-5", 0, 0) == 0.0


def test_opus_pricing() -> None:
    # Anthropic dropped Opus pricing to $5/$25 with the 4-6 release
    # (verified 2026-05-21). 1000 in + 1000 out:
    #   1000 * 5/1M + 1000 * 25/1M = 0.005 + 0.025 = 0.030
    cost = estimate_cost_usd("claude-opus-4-7", 1000, 1000)
    assert cost == pytest.approx(0.030)


def test_haiku_pricing() -> None:
    # 1000 in * 1/1M + 1000 out * 5/1M = 0.001 + 0.005 = 0.006
    cost = estimate_cost_usd("claude-haiku-4-5", 1000, 1000)
    assert cost == pytest.approx(0.006)


def test_family_prefix_when_subversion_unknown() -> None:
    # `claude-haiku-9` not in table — falls back to `claude-haiku`.
    cost = estimate_cost_usd("claude-haiku-9", 1000, 1000)
    assert cost == pytest.approx(0.006)
