"""`ab register` — register a results repo with the leaderboard server."""

from __future__ import annotations

import os

import httpx
import typer

from ..auth._http import get_http_client
from ..auth.credentials import load_credentials, save_credentials
from ..auth.device_flow import device_flow_login
from ..auth.repos_store import RegisteredRepo, add_repo
from ..ui import console

_FALLBACK_CLIENT_ID = "Iv1.test-client-id-placeholder"


def _resolve_client_id(
    explicit: str | None,
    server: str,
    *,
    http_client: httpx.Client | None = None,
) -> str:
    if explicit:
        return explicit
    env = os.environ.get("AB_GITHUB_CLIENT_ID")
    if env:
        return env
    owns = http_client is None
    client = http_client if http_client is not None else get_http_client()
    try:
        url = f"{server.rstrip('/')}/api/v1/auth/github/client-id"
        try:
            resp = client.get(url)
            if resp.status_code == 200:
                data = resp.json()
                cid = data.get("client_id")
                if isinstance(cid, str) and cid:
                    return cid
        except httpx.HTTPError:
            pass
    finally:
        if owns:
            client.close()
    return _FALLBACK_CLIENT_ID


def register(
    repo_url: str = typer.Argument(..., help="HTTPS URL of the results repository."),
    default_branch: str = typer.Option("main", help="Default branch the server will pull from."),
    server: str = typer.Option("http://localhost:8000", help="Leaderboard server base URL."),
    client_id: str | None = typer.Option(
        None, "--client-id", help="GitHub OAuth client id (override server lookup)."
    ),
) -> None:
    """Register a results repo with the leaderboard server (GitHub OAuth device flow)."""
    server_norm = server.rstrip("/")

    creds = load_credentials(server_norm)
    if creds is None:
        resolved_client_id = _resolve_client_id(client_id, server_norm)
        console.print(f"[dim]starting GitHub device-flow login (client_id={resolved_client_id})[/dim]")
        try:
            creds = device_flow_login(resolved_client_id, server_url=server_norm)
        except Exception as exc:
            console.print(f"[red]device-flow login failed:[/red] {exc}")
            raise typer.Exit(1) from exc
        save_credentials(creds)
        console.print(f"[green]authenticated as[/green] {creds.github_login}")
    else:
        console.print(f"[dim]using cached credentials for {creds.github_login}[/dim]")

    payload = {
        "repo_url": repo_url,
        "default_branch": default_branch,
        "is_public": True,
    }
    headers = {"Authorization": f"Bearer {creds.access_token}"}

    with get_http_client() as client:
        try:
            resp = client.post(
                f"{server_norm}/api/v1/repos",
                json=payload,
                headers=headers,
            )
        except httpx.HTTPError as exc:
            console.print(f"[red]POST /api/v1/repos failed:[/red] {exc}")
            raise typer.Exit(1) from exc

    if resp.status_code not in (200, 201):
        console.print(
            f"[red]server returned {resp.status_code}:[/red]\n{resp.text}"
        )
        raise typer.Exit(1)

    try:
        body = resp.json()
    except ValueError as exc:
        console.print(f"[red]server response is not JSON:[/red] {resp.text}")
        raise typer.Exit(1) from exc

    repo_id = body.get("id") or body.get("repo_id")
    if not repo_id:
        console.print(f"[red]server response missing repo id:[/red] {body}")
        raise typer.Exit(1)

    add_repo(
        server_norm,
        RegisteredRepo(
            id=str(repo_id),
            repo_url=repo_url,
            default_branch=default_branch,
        ),
    )

    console.print(
        f"[green]registered[/green] {repo_url} (id={repo_id}, branch={default_branch}) "
        f"with {server_norm}"
    )
