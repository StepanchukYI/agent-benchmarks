"""Registry sanity — verifies counts, vendor base URLs, lookup semantics.

NOT a pricing assertion suite (that's `test_pricing.py`). Here we lock the
SHAPE of the registry so future edits don't accidentally drop families or
break the runner factory.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest
from ab_harness.models import (
    DEFERRED_SCAFFOLDS,
    LOCAL_BASE_URLS,
    MODEL_REGISTRY,
    PRIORITY_SCAFFOLDS_V1,
    VENDOR_BASE_URLS,
    get_model_info,
    list_models,
    local_base_url,
    models_by_family,
    models_for_runner,
    runners_for_model,
    vendor_base_url,
)


def test_registry_is_non_empty() -> None:
    assert len(MODEL_REGISTRY) > 0


def test_every_entry_has_runners() -> None:
    """A model with zero compatible runners is unreachable — registry bug."""
    for m in MODEL_REGISTRY:
        assert m.compatible_runners, f"{m.id!r} has no runners"


def test_every_local_entry_is_zero_priced() -> None:
    """Self-hosted = no provider bill."""
    for m in MODEL_REGISTRY:
        if m.local:
            assert m.input_usd_per_1m == 0.0, f"{m.id!r} local but priced"
            assert m.output_usd_per_1m == 0.0, f"{m.id!r} local but priced"


def test_every_anthropic_compat_url_is_https() -> None:
    """Don't leak hosted endpoints over plaintext."""
    for m in MODEL_REGISTRY:
        url = m.anthropic_compat_base_url
        if url is not None:
            assert url.startswith("https://"), f"{m.id!r} compat url not https"


def test_all_vendor_base_urls_https() -> None:
    for vendor, url in VENDOR_BASE_URLS.items():
        assert url.startswith("https://"), f"{vendor!r} → {url}"


def test_local_base_urls_are_loopback() -> None:
    for scaffold, url in LOCAL_BASE_URLS.items():
        assert "://localhost" in url, f"{scaffold!r} → {url}"


@pytest.mark.parametrize(
    "model_id",
    [
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
        "gpt-5.5",
        "gpt-5.4",
        "gpt-5.3-codex",
        "o4-mini",
        "gemini-3.1-pro-preview",
        "gemini-2.5-flash",
        "deepseek-v4-flash",
        "glm-4.6",
        "kimi-k2.6",
        "qwen3-max",
        "MiniMax-M2.7",
        # Local
        "gemma3-27b",
        "llama-4-scout-17b-16e",
        "qwen3-coder-30b-a3b",
        "hermes-4-405b",
        "phi-4-reasoning",
    ],
)
def test_required_models_present(model_id: str) -> None:
    info = get_model_info(model_id)
    assert info is not None, f"{model_id!r} not in registry"
    assert info.id == model_id


def test_get_model_info_alias_match() -> None:
    """`gemini-3-pro` is an alias of `gemini-3.1-pro-preview`."""
    info = get_model_info("gemini-3-pro")
    assert info is not None
    assert info.id == "gemini-3.1-pro-preview"


def test_get_model_info_prefix_match_longest_wins() -> None:
    """Snapshot ids like `claude-opus-4-7-20260101` resolve to the alias root."""
    info = get_model_info("claude-opus-4-7-20260101")
    assert info is not None
    assert info.id == "claude-opus-4-7"


def test_get_model_info_unknown_returns_none() -> None:
    assert get_model_info("not-a-model") is None
    assert get_model_info("") is None


def test_models_for_runner_claude_code() -> None:
    models = models_for_runner("claude-code")
    families = {m.family for m in models}
    assert "claude" in families


def test_models_for_runner_local() -> None:
    models = models_for_runner("local")
    assert all(m.local for m in models)
    families = {m.family for m in models}
    # Must cover at least Gemma + Llama + Qwen + Hermes locally.
    for required in ("gemma", "llama", "qwen", "hermes"):
        assert required in families, f"local missing {required!r}"


def test_runners_for_model_kimi() -> None:
    """Kimi reaches us via anthropic-compat or opencode."""
    runners = runners_for_model("kimi-k2.6")
    assert "anthropic-compat" in runners
    assert "opencode" in runners


def test_models_by_family() -> None:
    claude = models_by_family("claude")
    assert {m.id for m in claude} >= {
        "claude-opus-4-7",
        "claude-sonnet-4-6",
        "claude-haiku-4-5",
    }


def test_list_models_filter_local() -> None:
    hosted = list_models(include_local=False)
    assert all(not m.local for m in hosted)
    all_models = list_models(include_local=True)
    assert len(all_models) > len(hosted)


def test_vendor_base_url_known() -> None:
    assert vendor_base_url("anthropic") == "https://api.anthropic.com"
    assert "bigmodel" in vendor_base_url("zhipu")
    assert "moonshot" in vendor_base_url("moonshot")
    assert "minimax" in vendor_base_url("minimax")
    assert "deepseek" in vendor_base_url("deepseek")


def test_vendor_base_url_unknown_falls_back_to_anthropic() -> None:
    """Typos route to Anthropic so the API call fails loudly on auth."""
    assert vendor_base_url("not-a-vendor") == VENDOR_BASE_URLS["anthropic"]


def test_local_base_url_defaults_to_ollama() -> None:
    assert local_base_url("unknown-scaffold") == LOCAL_BASE_URLS["ollama"]


def test_local_base_url_known_scaffolds() -> None:
    assert ":11434/v1" in local_base_url("ollama")
    assert ":1234/v1" in local_base_url("lmstudio")
    assert ":8000/v1" in local_base_url("vllm")
    assert ":8080/v1" in local_base_url("llamacpp")


def test_priority_and_deferred_scaffolds_disjoint() -> None:
    """A scaffold can't be both v1-priority and deferred."""
    assert not (set(PRIORITY_SCAFFOLDS_V1) & set(DEFERRED_SCAFFOLDS))


def test_priority_scaffolds_have_at_least_one_model_each() -> None:
    """v1 scaffolds must drive at least one model — otherwise they're stubs."""
    for scaffold in PRIORITY_SCAFFOLDS_V1:
        models = models_for_runner(scaffold)
        assert models, f"v1 scaffold {scaffold!r} drives no models"


def test_model_info_is_frozen() -> None:
    """ModelInfo is immutable so it can be safely shared across threads."""
    m = MODEL_REGISTRY[0]
    with pytest.raises(FrozenInstanceError):
        m.input_usd_per_1m = 999.0  # type: ignore[misc]


def test_no_duplicate_ids() -> None:
    ids = [m.id for m in MODEL_REGISTRY]
    assert len(ids) == len(set(ids)), "duplicate ids in registry"
