"""GitHub OAuth device flow (RFC 8628) — CLI side only."""

from __future__ import annotations

import contextlib
import time
import webbrowser
from collections.abc import Callable

import httpx

from ..ui import console
from ._http import get_http_client
from .credentials import Credentials

DEVICE_CODE_URL = "https://github.com/login/device/code"
ACCESS_TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"

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


def _request_device_code(client: httpx.Client, client_id: str, scope: str) -> dict:
    resp = client.post(
        DEVICE_CODE_URL,
        data={"client_id": client_id, "scope": scope},
    )
    resp.raise_for_status()
    payload = resp.json()
    for key in ("device_code", "user_code", "verification_uri", "interval", "expires_in"):
        if key not in payload:
            raise DeviceFlowError(f"device code response missing {key!r}: {payload}")
    return payload


def _poll_for_token(
    client: httpx.Client,
    *,
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
            ACCESS_TOKEN_URL,
            data={
                "client_id": client_id,
                "device_code": device_code,
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            },
        )
        resp.raise_for_status()
        payload = resp.json()
        if "access_token" in payload:
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
        raise DeviceFlowError(f"unexpected token response: {payload}")


def _fetch_github_login(client: httpx.Client, access_token: str) -> str:
    resp = client.get(
        USER_URL,
        headers={
            "Authorization": f"Bearer {access_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        },
    )
    resp.raise_for_status()
    payload = resp.json()
    login = payload.get("login")
    if not isinstance(login, str) or not login:
        raise DeviceFlowError(f"/user response missing 'login': {payload}")
    return login


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
    """Run device flow against github.com; return ``Credentials`` for ``server_url``.

    HTTP client is injectable for tests (use ``httpx.MockTransport``).
    """
    owns_client = http_client is None
    client = http_client if http_client is not None else get_http_client()
    try:
        code_data = _request_device_code(client, client_id, scope)
        callback = on_user_code or _default_on_user_code
        callback(
            code_data["user_code"],
            code_data["verification_uri"],
            int(code_data["expires_in"]),
        )
        token_payload = _poll_for_token(
            client,
            client_id=client_id,
            device_code=code_data["device_code"],
            interval=int(code_data["interval"]),
            expires_in=int(code_data["expires_in"]),
            sleep=sleep,
            now=now,
        )
        login = _fetch_github_login(client, token_payload["access_token"])
        return Credentials(
            access_token=token_payload["access_token"],
            scope=str(token_payload.get("scope", scope)),
            token_type=str(token_payload.get("token_type", "bearer")),
            github_login=login,
            server_url=server_url.rstrip("/"),
            expires_at=None,
        )
    finally:
        if owns_client:
            client.close()


__all__ = ["DeviceFlowError", "device_flow_login"]
