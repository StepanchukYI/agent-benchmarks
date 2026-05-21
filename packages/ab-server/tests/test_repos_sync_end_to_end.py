from __future__ import annotations

import json
import shutil
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


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


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=str(cwd), check=True, capture_output=True, env=_git_env()
    )


def _make_source_repo(root: Path) -> Path:
    source = root / "source"
    source.mkdir()
    _git(source, "init", "--initial-branch=main")
    run_dir = source / "results" / "20260521T000000Z-run-1"
    run_dir.mkdir(parents=True)
    (run_dir / "metadata.yaml").write_text(
        "run_id: run-1\n"
        "task_id: L0_001\n"
        "model: claude-sonnet\n"
        "tier: T0\n"
        "suite: file-ops\n"
        "dataset_version: ab-datasets==0.0.1\n"
        "harness: claude-code-cli@0.4.1\n"
        "started_at: 2026-05-21T00:00:00Z\n"
        "finished_at: 2026-05-21T00:00:01Z\n"
        "tier_hash: 'sha256:0'\n"
    )
    (run_dir / "scores.json").write_text(
        json.dumps(
            {
                "run_id": "run-1",
                "task_id": "L0_001",
                "model": "claude-sonnet",
                "tier": "T0",
                "dataset_version": "ab-datasets==0.0.1",
                "total_score": 1.0,
                "pass": True,
                "verdicts": [],
            }
        )
        + "\n"
    )
    events = [
        {
            "event": "run_start",
            "run_id": "run-1",
            "task_id": "L0_001",
            "model": "claude-sonnet",
            "harness": "claude-code-cli@0.4.1",
            "tier": "T0",
            "tier_hash": "sha256:0",
            "dataset_version": "ab-datasets==0.0.1",
            "prompt_template_hash": None,
            "started_at": "2026-05-21T00:00:00Z",
        },
        {
            "event": "turn",
            "idx": 0,
            "role": "assistant",
            "tool_calls": [
                {
                    "name": "write_file",
                    "args": {"path": "notes/greeting.txt", "content": "Hello, Example.\n"},
                }
            ],
            "tool_returns": [
                {"path": "notes/greeting.txt", "content": "Hello, Example.\n"}
            ],
            "model_output": "wrote file",
            "vault_state_diff": {"created": ["notes/greeting.txt"], "modified": [], "deleted": []},
            "tokens_in": 12,
            "tokens_out": 6,
            "latency_ms": 100,
            "cost_usd": 0.0,
        },
        {
            "event": "run_end",
            "finished_at": "2026-05-21T00:00:14Z",
            "status": "completed",
            "totals": {
                "tokens_in": 12,
                "tokens_out": 6,
                "latency_ms": 100,
                "cost_usd": 0.0,
                "score": 1.0,
            },
        },
    ]
    with (run_dir / "trajectory.jsonl").open("w") as fh:
        for ev in events:
            fh.write(json.dumps(ev) + "\n")

    _git(source, "add", "-A")
    _git(source, "commit", "-m", "initial")
    return source


@pytest.fixture()
def app_engine(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[object]:
    monkeypatch.setenv("AB_TEST_AUTH", "1")
    monkeypatch.setenv("FETCHER_CACHE_DIR", str(tmp_path / "cache"))

    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)

    def _override_session() -> Iterator[Session]:
        with Session(engine) as session:
            yield session

    app.dependency_overrides[get_session] = _override_session
    try:
        yield engine
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_end_to_end_sync_creates_verified_submission(
    tmp_path: Path,
    app_engine: object,
) -> None:
    if shutil.which("git") is None:
        pytest.skip("git not available")

    source = _make_source_repo(tmp_path)
    client = TestClient(app)

    register = client.post(
        "/api/v1/repos",
        json={"repo_url": str(source), "default_branch": "main", "is_public": True},
        headers={"X-Test-User": "alice"},
    )
    assert register.status_code == 201, register.text
    repo_id = register.json()["id"]

    sync = client.post(
        f"/api/v1/repos/{repo_id}/sync",
        headers={"X-Test-User": "alice"},
    )
    assert sync.status_code == 200, sync.text
    body = sync.json()
    assert body["inserted"] == 1
    assert body["rescored"] == 1
    assert body["errors"] == []

    listing = client.get(
        "/api/v1/submissions?trust=verified",
        headers={"X-Test-User": "alice"},
    )
    assert listing.status_code == 200
    items = listing.json()["items"]
    assert len(items) == 1
    assert items[0]["task_id"] == "L0_001"
    assert items[0]["trust_tier"] == "verified"

    detail = client.get(
        f"/api/v1/submissions/{items[0]['id']}",
        headers={"X-Test-User": "alice"},
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["submission"]["trust_tier"] == "verified"
    assert body["task_result"]["task_id"] == "L0_001"
    assert len(body["verdicts"]) >= 1

    second = client.post(
        f"/api/v1/repos/{repo_id}/sync",
        headers={"X-Test-User": "alice"},
    )
    assert second.status_code == 200
    assert second.json()["inserted"] == 0
