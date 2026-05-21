"""ProxyHeadersMiddleware must not trust arbitrary peers.

Previously the middleware was wired with ``trusted_hosts="*"``, which let any
container on the docker bridge spoof ``X-Forwarded-For`` and bypass per-IP
rate limiting. We now read the allow-list from ``Settings.proxy_trusted_hosts``
(default ``127.0.0.1``) and pass it as a list.

These tests exercise uvicorn's ``ProxyHeadersMiddleware`` directly with a
fake ASGI scope so we can control the peer ``client`` tuple — TestClient
always reports a localhost peer, which would be trusted under any sensible
default and so wouldn't prove anything.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from ab_server.config import Settings
from ab_server.main import create_app
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware


async def _capture_app(scope: dict[str, Any], receive: Any, send: Any) -> None:
    """Dummy ASGI app that records the (post-middleware) scope for inspection."""
    scope.setdefault("_captured", []).append(dict(scope))
    await send({"type": "http.response.start", "status": 204, "headers": []})
    await send({"type": "http.response.body", "body": b""})


def _make_scope(*, client_host: str, xff: str | None) -> dict[str, Any]:
    headers: list[tuple[bytes, bytes]] = []
    if xff is not None:
        headers.append((b"x-forwarded-for", xff.encode("latin1")))
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "http",
        "path": "/",
        "raw_path": b"/",
        "query_string": b"",
        "headers": headers,
        "client": (client_host, 12345),
        "server": ("server", 80),
    }


def _run(scope: dict[str, Any], middleware: ProxyHeadersMiddleware) -> dict[str, Any]:
    sent: list[dict[str, Any]] = []

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: dict[str, Any]) -> None:
        sent.append(message)

    asyncio.run(middleware(scope, receive, send))
    return scope


def test_untrusted_peer_xff_is_ignored() -> None:
    """A request from 10.0.0.5 with X-Forwarded-For: 1.2.3.4 must NOT rewrite client."""
    settings = Settings(ab_trust_proxy=True, proxy_trusted_hosts="127.0.0.1")
    trusted = [h.strip() for h in settings.proxy_trusted_hosts.split(",") if h.strip()]
    middleware = ProxyHeadersMiddleware(_capture_app, trusted_hosts=trusted)

    scope = _make_scope(client_host="10.0.0.5", xff="1.2.3.4")
    _run(scope, middleware)

    # client must remain the actual peer — XFF was not trusted.
    assert scope["client"][0] == "10.0.0.5"


def test_trusted_peer_xff_is_honoured() -> None:
    """A request from 127.0.0.1 with X-Forwarded-For: 1.2.3.4 rewrites client to 1.2.3.4."""
    settings = Settings(ab_trust_proxy=True, proxy_trusted_hosts="127.0.0.1")
    trusted = [h.strip() for h in settings.proxy_trusted_hosts.split(",") if h.strip()]
    middleware = ProxyHeadersMiddleware(_capture_app, trusted_hosts=trusted)

    scope = _make_scope(client_host="127.0.0.1", xff="1.2.3.4")
    _run(scope, middleware)

    assert scope["client"][0] == "1.2.3.4"


def test_wildcard_not_used_in_app_defaults() -> None:
    """Settings default must NOT be wildcard — that would re-introduce the bug."""
    settings = Settings()
    assert settings.proxy_trusted_hosts != "*"
    assert "*" not in [h.strip() for h in settings.proxy_trusted_hosts.split(",")]


def test_create_app_passes_list_not_wildcard() -> None:
    """When trust_proxy=True, ProxyHeadersMiddleware is added with a list, not '*'."""
    settings = Settings(ab_trust_proxy=True, proxy_trusted_hosts="127.0.0.1,10.0.0.1")
    app = create_app(settings)

    proxy_entries = [
        entry for entry in app.user_middleware if entry.cls is ProxyHeadersMiddleware
    ]
    assert len(proxy_entries) == 1
    entry = proxy_entries[0]
    # Starlette stores middleware kwargs on ``entry.kwargs``.
    trusted = entry.kwargs.get("trusted_hosts")
    assert isinstance(trusted, list), f"expected list, got {type(trusted).__name__}"
    assert "127.0.0.1" in trusted
    assert "10.0.0.1" in trusted
    assert "*" not in trusted


def test_empty_setting_falls_back_to_localhost() -> None:
    """An empty PROXY_TRUSTED_HOSTS must not silently become wildcard."""
    settings = Settings(ab_trust_proxy=True, proxy_trusted_hosts="")
    app = create_app(settings)

    proxy_entries = [
        entry for entry in app.user_middleware if entry.cls is ProxyHeadersMiddleware
    ]
    assert len(proxy_entries) == 1
    trusted = proxy_entries[0].kwargs.get("trusted_hosts")
    assert trusted == ["127.0.0.1"], (
        f"empty setting must default to localhost only, got {trusted!r}"
    )


def test_no_middleware_when_trust_proxy_disabled() -> None:
    """When AB_TRUST_PROXY=0, no ProxyHeadersMiddleware is added at all."""
    settings = Settings(ab_trust_proxy=False)
    app = create_app(settings)

    proxy_entries = [
        entry for entry in app.user_middleware if entry.cls is ProxyHeadersMiddleware
    ]
    assert proxy_entries == []


# Pytest doesn't need the ``pytest`` import for these straight asserts, but
# keeping it makes future parametrize/skip additions cheap.
_ = pytest
