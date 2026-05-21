from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


def clone_or_pull(repo_url: str, default_branch: str, dest: Path) -> str:
    """Shallow-clone (or refresh) repo_url into dest. Returns HEAD sha."""
    dest = Path(dest)
    if (dest / ".git").exists():
        subprocess.run(
            ["git", "fetch", "--depth=1", "origin", default_branch],
            cwd=str(dest),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "reset", "--hard", f"origin/{default_branch}"],
            cwd=str(dest),
            check=True,
            capture_output=True,
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
        )

    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"],
        cwd=str(dest),
        check=True,
        capture_output=True,
        text=True,
    )
    return sha.stdout.strip()
