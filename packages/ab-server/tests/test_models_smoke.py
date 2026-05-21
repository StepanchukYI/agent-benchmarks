from __future__ import annotations

from ab_server.models import RegisteredRepo, User
from sqlmodel import Session, SQLModel, create_engine, select


def test_user_and_repo_round_trip() -> None:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SQLModel.metadata.create_all(engine)

    with Session(engine) as session:
        user = User(github_id="gh-1", handle="alice", avatar_url=None)
        session.add(user)
        session.commit()
        session.refresh(user)

        repo = RegisteredRepo(
            user_id=user.id,
            repo_url="https://github.com/alice/results",
            default_branch="main",
            is_public=True,
        )
        session.add(repo)
        session.commit()
        session.refresh(repo)

        loaded_user = session.exec(select(User).where(User.github_id == "gh-1")).one()
        loaded_repo = session.exec(
            select(RegisteredRepo).where(RegisteredRepo.user_id == loaded_user.id)
        ).one()

        assert loaded_user.handle == "alice"
        assert loaded_repo.repo_url == "https://github.com/alice/results"
        assert loaded_repo.status == "registered"
        assert loaded_repo.is_public is True
