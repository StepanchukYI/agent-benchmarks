"""Error-path device-flow tests: slow_down, access_denied, expired_token."""

from __future__ import annotations

import httpx
import pytest
from ab_cli.auth._http import get_http_client
from ab_cli.auth.device_flow import DeviceFlowError, device_flow_login


def _make_transport(poll_responses: list[dict]):
    state = {"i": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/login/device/code"):
            return httpx.Response(
                200,
                json={
                    "device_code": "DEV",
                    "user_code": "AAAA-BBBB",
                    "verification_uri": "https://github.com/login/device",
                    "interval": 5,
                    "expires_in": 900,
                },
            )
        if url.endswith("/login/oauth/access_token"):
            resp = poll_responses[min(state["i"], len(poll_responses) - 1)]
            state["i"] += 1
            return httpx.Response(200, json=resp)
        if url.endswith("/user"):
            return httpx.Response(200, json={"login": "octocat"})
        return httpx.Response(404, json={})

    return httpx.MockTransport(handler)


def test_slow_down_increases_interval() -> None:
    transport = _make_transport(
        [
            {"error": "slow_down"},
            {"error": "authorization_pending"},
            {"access_token": "tok", "scope": "public_repo", "token_type": "bearer"},
        ]
    )
    sleeps: list[float] = []
    client = get_http_client(transport=transport)
    try:
        device_flow_login(
            "client",
            server_url="http://srv",
            http_client=client,
            on_user_code=lambda *_a: None,
            sleep=lambda s: sleeps.append(s),
            now=lambda: 0.0,
        )
    finally:
        client.close()

    assert sleeps[0] == 5
    assert sleeps[1] == 10
    assert sleeps[2] == 10


def test_access_denied_raises() -> None:
    transport = _make_transport([{"error": "access_denied"}])
    client = get_http_client(transport=transport)
    try:
        with pytest.raises(DeviceFlowError, match="denied"):
            device_flow_login(
                "client",
                server_url="http://srv",
                http_client=client,
                on_user_code=lambda *_a: None,
                sleep=lambda _s: None,
                now=lambda: 0.0,
            )
    finally:
        client.close()


def test_expired_token_raises() -> None:
    transport = _make_transport([{"error": "expired_token"}])
    client = get_http_client(transport=transport)
    try:
        with pytest.raises(DeviceFlowError, match="expired"):
            device_flow_login(
                "client",
                server_url="http://srv",
                http_client=client,
                on_user_code=lambda *_a: None,
                sleep=lambda _s: None,
                now=lambda: 0.0,
            )
    finally:
        client.close()
