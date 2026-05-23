"""Tests for GET /api/v1/leaderboard/prompt/{prompt_hash}."""
from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from ab_server.db import get_session
from ab_server.main import app
from ab_server.models import PromptBlob
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine


def _make_engine(tmp_path: Path):
    db_path = tmp_path / "test.db"
    engine = create_engine(
        f"sqlite:///{db_path}", connect_args={"check_same_thread": False}
    )
    SQLModel.metadata.create_all(engine)
    return engine


def _client(engine) -> TestClient:
    def _override_session() -> Iterator[Session]:
        with Session(engine) as s:
            yield s

    app.dependency_overrides[get_session] = _override_session
    return TestClient(app)


def test_prompt_reveal_blob_present(tmp_path: Path) -> None:
    """Known hash from prompt_blobs → 200 with label and text."""
    engine = _make_engine(tmp_path)
    with Session(engine) as session:
        blob = PromptBlob(
            prompt_hash="abc123",
            text="You are a strict code reviewer.",
            label="strict-reviewer",
        )
        session.add(blob)
        session.commit()

    client = _client(engine)
    try:
        resp = client.get("/api/v1/leaderboard/prompt/abc123")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["text"] == "You are a strict code reviewer."
        assert body["label"] == "strict-reviewer"
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_prompt_reveal_blob_null_label(tmp_path: Path) -> None:
    """Blob with no label → 200, label is null."""
    engine = _make_engine(tmp_path)
    with Session(engine) as session:
        blob = PromptBlob(
            prompt_hash="nolabel",
            text="Some prompt text.",
            label=None,
        )
        session.add(blob)
        session.commit()

    client = _client(engine)
    try:
        resp = client.get("/api/v1/leaderboard/prompt/nolabel")
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["label"] is None
        assert body["text"] == "Some prompt text."
    finally:
        app.dependency_overrides.pop(get_session, None)


def test_prompt_reveal_unknown_hash_404(tmp_path: Path) -> None:
    """Unknown hash → 404."""
    engine = _make_engine(tmp_path)
    client = _client(engine)
    try:
        resp = client.get("/api/v1/leaderboard/prompt/doesnotexist")
        assert resp.status_code == 404
        assert resp.json()["detail"] == "prompt not found"
    finally:
        app.dependency_overrides.pop(get_session, None)
