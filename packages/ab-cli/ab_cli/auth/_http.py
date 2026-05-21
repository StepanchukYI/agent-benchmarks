"""Thin httpx wrapper used by the auth + repo-registration flows."""

from __future__ import annotations

import os

import httpx

from .. import __version__

USER_AGENT = f"agent-benchmarks-cli/{__version__}"
_DEFAULT_TIMEOUT = 30.0


def _timeout() -> float:
    raw = os.environ.get("AB_HTTP_TIMEOUT")
    if not raw:
        return _DEFAULT_TIMEOUT
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_TIMEOUT


def get_http_client(
    *,
    transport: httpx.BaseTransport | None = None,
    accept_json: bool = True,
) -> httpx.Client:
    headers: dict[str, str] = {"User-Agent": USER_AGENT}
    if accept_json:
        headers["Accept"] = "application/json"
    return httpx.Client(
        transport=transport,
        timeout=_timeout(),
        headers=headers,
    )


__all__ = ["USER_AGENT", "get_http_client"]
