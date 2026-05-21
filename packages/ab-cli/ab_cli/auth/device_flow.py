"""GitHub OAuth device flow — CLI side.

The CLI does NOT talk to github.com directly. It drives the device flow
through the leaderboard server's endpoints, which mint a *server session
token* (not a GitHub access token). The session token is what every
authenticated `ab` command sends as `Authorization: Bearer <token>`.

Flow:
  1. GET  {server}/api/v1/auth/github/client-id  → effective client_id
  2. POST {server}/api/v1/auth/github/device-start
     →  {device_code, user_code, verification_uri, interval, expires_in}
  3. User opens verification_uri, enters user_code on github.com
  4. POST {server}/api/v1/auth/github/device-poll every `interval` seconds
     →  authorization_pending | slow_down | {access_token, github_login,
        expires_at} (access_token is the server session token)

If the CLI talked to github.com directly it would only receive a GitHub
API token, which the server cannot validate against the users table —
that path returned 401 "invalid token" on every subsequent request.
"""

from __future__ import annotations

import contextlib
import time
import webbrowser
from collections.abc import Callable

import httpx

from ..ui import console
from ._http import get_http_client
from .credentials import Credentials

OnUserCode = Callable[[str, str, int], None]


class DeviceFlowError(RuntimeError):
    """Raised when the device flow cannot complete."""


def _default_on_user_code(user_code: str, verification_uri: str, expires_in: int) -> None:
    console.print(
        f"[bold]Open[/bold] {verification_uri} [bold]and enter code:[/bold] "
        f"[cyan]{user_code}[/cyan]  (expires in {expires_in}s)"
    )
    with contextlib.suppress(Exception):
        webbrowser.open(verification_uri)


def _start_device(client: httpx.Client, server_url: str, client_id: str) -> dict:
    resp = client.post(
        f"{server_url}/api/v1/auth/github/device-start",
        json={"client_id": client_id},
        headers={"Accept": "application/json"},
    )
    if resp.status_code >= 400:
        raise DeviceFlowError(
            f"server /auth/github/device-start returned {resp.status_code}: {resp.text[:300]}"
        )
    payload = resp.json()
    for key in ("device_code", "user_code", "verification_uri", "interval", "expires_in"):
        if key not in payload:
            raise DeviceFlowError(f"device-start response missing {key!r}: {payload}")
    return payload


def _poll_server(
    client: httpx.Client,
    *,
    server_url: str,
    client_id: str,
    device_code: str,
    interval: int,
    expires_in: int,
    sleep: Callable[[float], None],
    now: Callable[[], float],
) -> dict:
    deadline = now() + expires_in
    current_interval = max(1, int(interval))
    while True:
        if now() >= deadline:
            raise DeviceFlowError("device flow expired before user authorized")
        sleep(current_interval)
        resp = client.post(
            f"{server_url}/api/v1/auth/github/device-poll",
            json={"client_id": client_id, "device_code": device_code},
            headers={"Accept": "application/json"},
        )
        if resp.status_code >= 500:
            raise DeviceFlowError(
                f"server /auth/github/device-poll returned {resp.status_code}: {resp.text[:300]}"
            )
        # 4xx may be pending/slow_down envelopes returned with 200 by spec,
        # but tolerate accidental 400 by surfacing the body.
        if resp.status_code >= 400:
            raise DeviceFlowError(
                f"server /auth/github/device-poll returned {resp.status_code}: {resp.text[:300]}"
            )
        payload = resp.json()
        # Success: server minted a session token.
        if "access_token" in payload and "error" not in payload:
            return payload
        err = payload.get("error")
        if err == "authorization_pending":
            continue
        if err == "slow_down":
            current_interval = current_interval + 5
            continue
        if err == "expired_token":
            raise DeviceFlowError("device flow expired before user authorized")
        if err == "access_denied":
            raise DeviceFlowError("user denied access during device flow")
        raise DeviceFlowError(f"unexpected device-poll response: {payload}")


def device_flow_login(
    client_id: str,
    *,
    server_url: str,
    http_client: httpx.Client | None = None,
    scope: str = "public_repo read:user",
    on_user_code: OnUserCode | None = None,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
) -> Credentials:
    """Run device flow against the leaderboard server; return ``Credentials``.

    The ``scope`` arg is no longer forwarded — the server fixes the scope
    when it talks to GitHub. Kept in the signature for backward compat
    with existing callers and tests that pass it positionally.

    HTTP client is injectable for tests (use ``httpx.MockTransport``).
    """
    server_norm = server_url.rstrip("/")
    owns_client = http_client is None
    client = http_client if http_client is not None else get_http_client()
    try:
        code_data = _start_device(client, server_norm, client_id)
        callback = on_user_code or _default_on_user_code
        callback(
            code_data["user_code"],
            code_data["verification_uri"],
            int(code_data["expires_in"]),
        )
        result = _poll_server(
            client,
            server_url=server_norm,
            client_id=client_id,
            device_code=code_data["device_code"],
            interval=int(code_data["interval"]),
            expires_in=int(code_data["expires_in"]),
            sleep=sleep,
            now=now,
        )
        # result = {access_token, github_login, expires_at}
        return Credentials(
            access_token=result["access_token"],
            scope=scope,
            token_type="bearer",
            github_login=str(result.get("github_login") or "unknown"),
            server_url=server_norm,
            expires_at=result.get("expires_at"),
        )
    finally:
        if owns_client:
            client.close()


__all__ = ["DeviceFlowError", "device_flow_login"]
