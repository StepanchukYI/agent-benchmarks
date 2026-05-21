"""`ab register` CLI test: mocks device_flow + POST /api/v1/repos."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
from ab_cli.auth.credentials import Credentials, credentials_path
from ab_cli.auth.repos_store import repos_path
from ab_cli.main import app
from typer.testing import CliRunner


@pytest.fixture
def isolated_config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    cfg = tmp_path / "xdg-config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(cfg))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "xdg-cache"))
    return cfg


def test_register_writes_credentials_and_repos(
    isolated_config: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_creds = Credentials(
        access_token="gh_token_xyz",
        scope="public_repo read:user",
        token_type="bearer",
        github_login="octocat",
        server_url="http://localhost:8000",
    )

    def fake_login(client_id: str, *, server_url: str, **kwargs):
        assert client_id
        assert server_url == "http://localhost:8000"
        return fake_creds

    monkeypatch.setattr("ab_cli.commands.register.device_flow_login", fake_login)

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url.endswith("/api/v1/auth/github/client-id"):
            return httpx.Response(200, json={"client_id": "Iv1.from-server"})
        if url.endswith("/api/v1/repos"):
            captured["method"] = request.method
            captured["headers"] = dict(request.headers)
            captured["body"] = json.loads(request.content)
            return httpx.Response(
                201,
                json={
                    "id": "repo_42",
                    "repo_url": "https://github.com/example/results.git",
                    "default_branch": "main",
                },
            )
        return httpx.Response(404, json={})

    mock_transport = httpx.MockTransport(handler)

    real_get_client = __import__("ab_cli.auth._http", fromlist=["get_http_client"]).get_http_client

    def get_client_with_mock(**kw):
        kw.pop("transport", None)
        return real_get_client(transport=mock_transport, **kw)

    monkeypatch.setattr("ab_cli.commands.register.get_http_client", get_client_with_mock)

    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "register",
            "https://github.com/example/results.git",
            "--default-branch",
            "main",
            "--server",
            "http://localhost:8000",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "registered" in result.output.lower()
    assert "repo_42" in result.output

    assert captured["method"] == "POST"
    assert captured["headers"].get("authorization") == "Bearer gh_token_xyz"
    assert captured["body"] == {
        "repo_url": "https://github.com/example/results.git",
        "default_branch": "main",
        "is_public": True,
    }

    creds_file = credentials_path()
    assert creds_file.exists()
    mode = creds_file.stat().st_mode & 0o777
    assert mode == 0o600

    repos_file = repos_path()
    assert repos_file.exists()
    with repos_file.open() as fh:
        stored = json.load(fh)
    assert "http://localhost:8000" in stored
    entries = stored["http://localhost:8000"]
    assert len(entries) == 1
    assert entries[0]["id"] == "repo_42"
    assert entries[0]["repo_url"] == "https://github.com/example/results.git"
    assert entries[0]["default_branch"] == "main"
