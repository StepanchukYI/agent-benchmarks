"""By-id submission detail endpoints must enforce the public-repo gate.

Regression for the audit finding: get_submission / trajectory / privacy-scan
resolved a submission by UUID with no is_public check, leaking private-repo
contents to anyone who could guess the id. The list endpoint already gated
on RegisteredRepo.is_public; the by-id handlers did not.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import RegisteredRepo, Submission, TaskResult, User
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


@pytest.fixture()
def seeded(tmp_path: Path) -> Iterator[tuple[TestClient, dict[str, str]]]:
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    ids: dict[str, str] = {}

    with Session(engine) as session:
        for tag, public in (("pub", True), ("priv", False)):
            user = User(github_id=f"u-{tag}", handle=f"{tag}user", avatar_url=None)
            session.add(user)
            session.commit()
            session.refresh(user)
            repo = RegisteredRepo(
                user_id=user.id,
                repo_url=f"https://github.com/{tag}user/results",
                default_branch="main",
                is_public=public,
                status="registered",
            )
            session.add(repo)
            session.commit()
            session.refresh(repo)
            sub = Submission(
                registered_repo_id=repo.id,
                source_commit_sha=f"sha-{tag}",
                source_path=f"results/{tag}-run",
                trust_tier="self_reported",
                model="claude-sonnet",
                tier="T0",
                dataset_version="ab-datasets==0.0.1",
            )
            session.add(sub)
            session.commit()
            session.refresh(sub)
            session.add(
                TaskResult(
                    submission_id=sub.id,
                    task_id="L0_001",
                    suite="file-ops",
                    model="claude-sonnet",
                    tier="T0",
                    tier_hash="sha256:0",
                    status="completed",
                    score_total=1.0 if public else 0.5,
                )
            )
            session.commit()
            ids[tag] = str(sub.id)

    def _override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    client = TestClient(app)
    try:
        yield client, ids
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_get_submission_public_ok(seeded: tuple[TestClient, dict[str, str]]) -> None:
    client, ids = seeded
    resp = client.get(f"/api/v1/submissions/{ids['pub']}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["submission"]["source_commit_sha"] == "sha-pub"


def test_get_submission_private_is_404(
    seeded: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = seeded
    resp = client.get(f"/api/v1/submissions/{ids['priv']}")
    assert resp.status_code == 404, (
        f"private-repo submission detail must 404, got {resp.status_code}: {resp.text}"
    )


def test_private_submission_trajectory_is_404(
    seeded: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = seeded
    resp = client.get(f"/api/v1/submissions/{ids['priv']}/trajectory")
    assert resp.status_code == 404, (
        f"private-repo trajectory must 404, got {resp.status_code}"
    )


def test_private_submission_privacy_scan_is_404(
    seeded: tuple[TestClient, dict[str, str]],
) -> None:
    client, ids = seeded
    resp = client.get(f"/api/v1/submissions/{ids['priv']}/privacy-scan")
    assert resp.status_code == 404, (
        f"private-repo privacy-scan must 404, got {resp.status_code}"
    )
