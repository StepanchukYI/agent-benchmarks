from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlparse

_DEFAULT_ALLOWED_HOSTS = ("github.com", "gitlab.com", "bitbucket.org", "codeberg.org")
_DEFAULT_TIMEOUT = 120


class RepoURLError(ValueError):
    """Raised when a registered repo URL is not safe to clone."""


def _allowed_hosts() -> tuple[str, ...]:
    env = os.environ.get("AB_FETCH_ALLOWED_HOSTS")
    if env:
        return tuple(h.strip() for h in env.split(",") if h.strip())
    return _DEFAULT_ALLOWED_HOSTS


def _timeout() -> int:
    try:
        return int(os.environ.get("AB_FETCH_TIMEOUT_SEC", _DEFAULT_TIMEOUT))
    except ValueError:
        return _DEFAULT_TIMEOUT


def _validate_repo_url(repo_url: str) -> None:
    """Reject schemes/hosts that could SSRF or hang the server."""
    if os.environ.get("AB_FETCH_ALLOW_LOCAL") == "1":
        # Test-only opt-in. Production runs MUST NOT set this.
        return
    if repo_url.startswith("file:") or repo_url.startswith("ssh:") or repo_url.startswith("git+ssh:"):
        raise RepoURLError(f"unsupported scheme in repo_url: {repo_url!r}")
    if repo_url.startswith("git@"):
        raise RepoURLError(f"SSH (git@) URLs not supported in v1: {repo_url!r}")
    if "://" not in repo_url:
        raise RepoURLError(f"repo_url must be an absolute https URL: {repo_url!r}")

    parsed = urlparse(repo_url)
    if parsed.scheme not in ("https", "http"):
        raise RepoURLError(f"only https/http allowed, got {parsed.scheme!r}")
    host = (parsed.hostname or "").lower()
    allowed = _allowed_hosts()
    if not any(host == h or host.endswith("." + h) for h in allowed):
        raise RepoURLError(
            f"host {host!r} not in AB_FETCH_ALLOWED_HOSTS={allowed!r}"
        )


def clone_or_pull(repo_url: str, default_branch: str, dest: Path) -> str:
    """Shallow-clone (or refresh) repo_url into dest. Returns HEAD sha."""
    _validate_repo_url(repo_url)
    dest = Path(dest)
    timeout = _timeout()
    if (dest / ".git").exists():
        subprocess.run(
            ["git", "fetch", "--depth=1", "origin", default_branch],
            cwd=str(dest),
            check=True,
            capture_output=True,
            timeout=timeout,
        )
        subprocess.run(
            ["git", "reset", "--hard", f"origin/{default_branch}"],
            cwd=str(dest),
            check=True,
            capture_output=True,
            timeout=timeout,
        )
    else:
        if dest.exists():
            shutil.rmtree(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth=1",
                "--branch",
                default_branch,
                repo_url,
                str(dest),
            ],
            check=True,
            capture_output=True,
            timeout=timeout,
        )

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(dest),
        check=True,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    return sha.stdout.strip()
