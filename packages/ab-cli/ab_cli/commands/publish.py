"""`ab publish` — privacy-gate + git add/commit/push wrapper for results repos."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from pathlib import Path

import typer

from ..auth.credentials import load_credentials
from ..auth.repos_store import RegisteredRepo, list_repos
from ..ui import console


def _cache_root() -> Path:
    base = os.environ.get("XDG_CACHE_HOME")
    if base:
        return Path(base) / "agent-benchmarks"
    return Path.home() / ".cache" / "agent-benchmarks"


def _clone_dir(repo_url: str) -> Path:
    digest = hashlib.sha1(repo_url.encode("utf-8")).hexdigest()
    return _cache_root() / "results-repos" / digest


def _pick_repo(
    server_url: str,
    explicit: str | None,
) -> RegisteredRepo:
    if explicit:
        for r in list_repos(server_url):
            if r.repo_url == explicit:
                return r
        return RegisteredRepo(id="local", repo_url=explicit, default_branch="main")
    candidates = list_repos(server_url)
    if not candidates:
        console.print(
            f"[red]no registered repos for {server_url}; run `ab register` first[/red]"
        )
        raise typer.Exit(2)
    if len(candidates) > 1:
        console.print(
            f"[red]multiple registered repos for {server_url}; pass --repo URL[/red]"
        )
        for r in candidates:
            console.print(f"  - {r.repo_url}")
        raise typer.Exit(2)
    return candidates[0]


def _enumerate_run_dirs(results_dir: Path) -> list[Path]:
    if not results_dir.exists():
        return []
    return sorted(p for p in results_dir.iterdir() if p.is_dir())


def _run_git(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        cwd=str(cwd) if cwd else None,
        check=True,
        capture_output=True,
        text=True,
    )


def _ensure_clone(repo_url: str, default_branch: str) -> Path:
    target = _clone_dir(repo_url)
    target.parent.mkdir(parents=True, exist_ok=True)
    if (target / ".git").exists():
        _run_git(["git", "fetch", "origin"], cwd=target)
        _run_git(["git", "checkout", default_branch], cwd=target)
        _run_git(["git", "pull", "--ff-only", "origin", default_branch], cwd=target)
        return target
    _run_git(["git", "clone", "--depth", "1", "--branch", default_branch, repo_url, str(target)])
    return target


def publish(
    results_dir: Path = typer.Option(
        Path("./results"), "--results-dir", help="Local results root."
    ),
    repo: str | None = typer.Option(None, "--repo", help="Override target repo URL."),
    server: str = typer.Option("http://localhost:8000", help="Leaderboard server base URL."),
    message: str = typer.Option("update results", "--message", "-m", help="Commit message."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Validate + report, do not push."),
) -> None:
    """Commit and push the local results dir to the registered repo (privacy-gated)."""
    from ab_sdk.publish_gate import check_publish_ready

    server_norm = server.rstrip("/")
    target = _pick_repo(server_norm, repo)

    run_dirs = _enumerate_run_dirs(Path(results_dir))
    if not run_dirs:
        console.print(f"[yellow]no run dirs under {results_dir}[/yellow]")
        raise typer.Exit(0)

    ready: list[Path] = []
    failed: list[tuple[Path, list[str]]] = []
    for rd in run_dirs:
        ok, issues = check_publish_ready(rd)
        if ok:
            ready.append(rd)
        else:
            failed.append((rd, issues))

    if failed:
        console.print(f"[red]privacy-gate failed for {len(failed)} run dir(s):[/red]")
        for rd, issues in failed:
            console.print(f"  - {rd.name}")
            for iss in issues:
                console.print(f"      - {iss}")
        if not dry_run:
            raise typer.Exit(1)

    if dry_run:
        console.print(
            f"[green]dry-run:[/green] would publish {len(ready)} run dir(s) "
            f"to {target.repo_url} (branch={target.default_branch})"
        )
        raise typer.Exit(0)

    if not ready:
        console.print("[yellow]no run dirs passed the privacy gate[/yellow]")
        raise typer.Exit(1)

    creds = load_credentials(server_norm)
    git_login = creds.github_login if creds else "anonymous"

    try:
        clone = _ensure_clone(target.repo_url, target.default_branch)
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]git clone/fetch failed:[/red]\n{exc.stderr or exc.stdout}")
        raise typer.Exit(1) from exc

    dest_root = clone / "results"
    dest_root.mkdir(parents=True, exist_ok=True)
    for rd in ready:
        dst = dest_root / rd.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(rd, dst)

    try:
        _run_git(["git", "add", "results"], cwd=clone)
        status_proc = _run_git(["git", "status", "--porcelain", "results"], cwd=clone)
        if not status_proc.stdout.strip():
            rev = _run_git(["git", "rev-parse", "HEAD"], cwd=clone)
            sha = rev.stdout.strip()
            console.print(
                f"[yellow]nothing to commit[/yellow] — {len(ready)} run dir(s) already match "
                f"{target.repo_url}@{target.default_branch} (sha={sha[:12]})"
            )
            return
        _run_git(
            [
                "git",
                "-c",
                "user.name=ab-cli",
                "-c",
                f"user.email={git_login}+ab-cli@users.noreply.github.com",
                "commit",
                "-m",
                message,
            ],
            cwd=clone,
        )
        _run_git(["git", "push", "origin", target.default_branch], cwd=clone)
        rev = _run_git(["git", "rev-parse", "HEAD"], cwd=clone)
        sha = rev.stdout.strip()
    except subprocess.CalledProcessError as exc:
        console.print(f"[red]git operation failed:[/red]\n{exc.stderr or exc.stdout}")
        raise typer.Exit(1) from exc

    console.print(
        f"[green]published[/green] {len(ready)} run dir(s) to "
        f"{target.repo_url}@{target.default_branch} (sha={sha[:12]})"
    )
