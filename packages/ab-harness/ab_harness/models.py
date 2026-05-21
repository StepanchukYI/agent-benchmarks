"""Model registry — vendor URLs + helper API.

The MODEL_REGISTRY list is intentionally left as a stub right now: an
explicit research pass against vendor pricing pages is in flight and the
catalog will be populated from that. Helpers and base-URL maps below
are stable infrastructure used by the runner factory — they don't depend
on which specific models are registered.

When the research lands, populate ``MODEL_REGISTRY`` with verified
``ModelInfo`` entries (current model IDs, current prices, current
context windows) — DO NOT seed it from training data.
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
    notes: str = ""
    aliases: tuple[str, ...] = field(default_factory=tuple)


# Populated from the live research pass — kept empty here until that lands.
# See packages/ab-harness/ab_harness/models.py history for the placeholder
# I removed because it was based on stale training data.
MODEL_REGISTRY: tuple[ModelInfo, ...] = ()


# Anthropic-compat base URLs. Each Chinese vendor + Anthropic itself.
# Populated incrementally as the research agent confirms each endpoint.
VENDOR_BASE_URLS: dict[str, str] = {
    "anthropic": "https://api.anthropic.com",
}


# Local-runner OpenAI-compat base URLs. These are infrastructure constants
# (the scaffold's default port) — not model data — so they stay even
# while MODEL_REGISTRY is empty.
LOCAL_BASE_URLS: dict[str, str] = {
    "ollama": "http://localhost:11434/v1",
    "lmstudio": "http://localhost:1234/v1",
    "vllm": "http://localhost:8000/v1",
    "llamacpp": "http://localhost:8080/v1",
    "textgen-webui": "http://localhost:5000/v1",
}


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
    "LOCAL_BASE_URLS",
    "MODEL_REGISTRY",
    "VENDOR_BASE_URLS",
    "ModelInfo",
    "get_model_info",
    "list_models",
    "local_base_url",
    "models_for_runner",
    "runners_for_model",
    "vendor_base_url",
]
