"""Happy-path device-flow test using httpx.MockTransport."""

from __future__ import annotations

import httpx
import pytest
from ab_cli.auth._http import get_http_client
from ab_cli.auth.device_flow import device_flow_login


@pytest.fixture
def transport_factory():
    def _make(poll_responses: list[dict]):
        state = {"poll_idx": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            url = str(request.url)
            if url.endswith("/login/device/code"):
                return httpx.Response(
                    200,
                    json={
                        "device_code": "DEV-CODE-XYZ",
                        "user_code": "AB12-CD34",
                        "verification_uri": "https://github.com/login/device",
                        "interval": 5,
                        "expires_in": 900,
                    },
                )
            if url.endswith("/login/oauth/access_token"):
                resp = poll_responses[min(state["poll_idx"], len(poll_responses) - 1)]
                state["poll_idx"] += 1
                return httpx.Response(200, json=resp)
            if url.endswith("/user"):
                return httpx.Response(200, json={"login": "octocat", "id": 583231})
            return httpx.Response(404, json={"error": "unknown route"})

        return httpx.MockTransport(handler)

    return _make


def test_device_flow_happy_path(transport_factory) -> None:
    transport = transport_factory(
        [
            {"error": "authorization_pending"},
            {"error": "authorization_pending"},
            {"access_token": "gh_xyz_secret", "scope": "public_repo,read:user", "token_type": "bearer"},
        ]
    )
    captured: dict = {}

    def on_code(user_code: str, verification_uri: str, expires_in: int) -> None:
        captured["user_code"] = user_code
        captured["uri"] = verification_uri
        captured["expires_in"] = expires_in

    sleeps: list[float] = []
    client = get_http_client(transport=transport)
    try:
        creds = device_flow_login(
            "Iv1.client",
            server_url="http://localhost:8000",
            http_client=client,
            on_user_code=on_code,
            sleep=lambda s: sleeps.append(s),
            now=lambda: 0.0,
        )
    finally:
        client.close()

    assert creds.access_token == "gh_xyz_secret"
    assert creds.github_login == "octocat"
    assert creds.server_url == "http://localhost:8000"
    assert creds.scope == "public_repo,read:user"
    assert creds.token_type == "bearer"
    assert captured["user_code"] == "AB12-CD34"
    assert captured["uri"] == "https://github.com/login/device"
    assert captured["expires_in"] == 900
    assert len(sleeps) == 3
    assert all(s == 5 for s in sleeps)
