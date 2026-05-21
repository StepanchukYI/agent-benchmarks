from __future__ import annotations

from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from ab_server.config import Settings


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    settings = Settings()
    url = settings.database_url
    # SQLite needs check_same_thread=False for FastAPI's threadpool model.
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, echo=False, connect_args=connect_args)


def init_db() -> None:
    SQLModel.metadata.create_all(get_engine())


def get_session() -> Iterator[Session]:
    with Session(get_engine()) as session:
        yield session
