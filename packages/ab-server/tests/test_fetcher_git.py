from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from ab_server.fetcher.git import clone_or_pull


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        check=True,
        capture_output=True,
        env=_git_env(),
    )


def _git_env() -> dict[str, str]:
    return {
        "GIT_AUTHOR_NAME": "Tester",
        "GIT_AUTHOR_EMAIL": "tester@example.com",
        "GIT_COMMITTER_NAME": "Tester",
        "GIT_COMMITTER_EMAIL": "tester@example.com",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "HOME": "/tmp",
        "PATH": "/usr/bin:/bin:/usr/local/bin",
    }


def _make_source_repo(root: Path) -> tuple[Path, Path]:
    source = root / "source"
    source.mkdir()
    _git(source, "init", "--initial-branch=main")
    (source / "results").mkdir()
    run_dir = source / "results" / "20260521T000000Z-run-1"
    run_dir.mkdir()
    (run_dir / "metadata.yaml").write_text(
        "run_id: run-1\ntask_id: L0_001\nmodel: claude-sonnet\ntier: T0\ndataset_version: 0.0.1\nharness: test\nstarted_at: 2026-05-21T00:00:00Z\nfinished_at: 2026-05-21T00:00:01Z\n"
    )
    (run_dir / "scores.json").write_text('{"run_id":"run-1","task_id":"L0_001","total_score":1.0,"pass":true}\n')
    (run_dir / "trajectory.jsonl").write_text("{}\n")
    _git(source, "add", "-A")
    _git(source, "commit", "-m", "initial")
    return source, run_dir


def test_clone_or_pull_returns_head_sha(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    monkeypatch.setenv("AB_FETCH_ALLOW_LOCAL", "1")

    source, _ = _make_source_repo(tmp_path)
    dest = tmp_path / "dest"
    head_sha = clone_or_pull(str(source), "main", dest)

    assert dest.exists()
    assert (dest / "results").is_dir()
    assert len(head_sha) >= 7
    assert head_sha.strip() == head_sha


def test_clone_or_pull_idempotent(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")
    monkeypatch.setenv("AB_FETCH_ALLOW_LOCAL", "1")
    source, _ = _make_source_repo(tmp_path)
    dest = tmp_path / "dest"
    sha1 = clone_or_pull(str(source), "main", dest)
    sha2 = clone_or_pull(str(source), "main", dest)
    assert sha1 == sha2


def test_clone_or_pull_rejects_file_scheme(tmp_path: Path) -> None:
    from ab_server.fetcher.git import RepoURLError
    with pytest.raises(RepoURLError):
        clone_or_pull("file:///etc/passwd", "main", tmp_path / "x")


def test_clone_or_pull_rejects_ssh_url(tmp_path: Path) -> None:
    from ab_server.fetcher.git import RepoURLError
    with pytest.raises(RepoURLError):
        clone_or_pull("git@github.com:foo/bar.git", "main", tmp_path / "x")


def test_clone_or_pull_rejects_disallowed_host(tmp_path: Path) -> None:
    from ab_server.fetcher.git import RepoURLError
    with pytest.raises(RepoURLError):
        clone_or_pull("https://attacker.example.com/foo.git", "main", tmp_path / "x")
