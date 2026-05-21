from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlmodel import Session, select

from ab_server.auth.dependency import get_current_user
from ab_server.db import get_session
from ab_server.leaderboard import RegistryRepoOut, ScrubberRule
from ab_server.models import RegisteredRepo, Submission, TaskResult, User

router = APIRouter(tags=["account"])


def _owner_from_url(url: str) -> str:
    if not url:
        return ""
    s = url.rstrip("/").removeprefix("https://").removeprefix("http://")
    s = s.removeprefix("github.com/").removeprefix("gitlab.com/")
    parts = s.split("/")
    return parts[0] if parts else ""


@router.get("/account/repos", response_model=list[RegistryRepoOut])
def list_account_repos(
    user: Annotated[User, Depends(get_current_user)],
    session: Annotated[Session, Depends(get_session)],
) -> list[RegistryRepoOut]:
    repos = session.exec(
        select(RegisteredRepo)
        .where(RegisteredRepo.user_id == user.id)
        .where(RegisteredRepo.status != "archived")
    ).all()

    runs_count: dict[str, int] = {}
    for repo in repos:
        count_stmt = (
            select(func.count(TaskResult.id))
            .select_from(TaskResult)
            .join(Submission, Submission.id == TaskResult.submission_id)
            .where(Submission.registered_repo_id == repo.id)
        )
        n = session.exec(count_stmt).one()
        if isinstance(n, tuple):
            n = n[0]
        runs_count[str(repo.id)] = int(n or 0)

    out: list[RegistryRepoOut] = []
    for repo in repos:
        if repo.last_synced_at is None:
            status = "pending"
            last_synced = "never"
        else:
            last_synced = repo.last_synced_at.isoformat()
            status = "ok" if repo.sync_cursor else "failed"
        out.append(
            RegistryRepoOut(
                repo=repo.repo_url,
                owner=_owner_from_url(repo.repo_url) or user.handle,
                branch=repo.default_branch,
                runs=runs_count.get(str(repo.id), 0),
                last_synced=last_synced,
                status=status,
                error=None,
            )
        )
    return out


def _privacy_patterns_path() -> Path | None:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        candidate = parent / "docs" / "privacy-patterns.yaml"
        if candidate.is_file():
            return candidate
    return None


@router.get("/account/privacy-rules", response_model=list[ScrubberRule])
def list_privacy_rules() -> list[ScrubberRule]:
    path = _privacy_patterns_path()
    if path is None:
        return []
    with path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    rules: list[ScrubberRule] = []
    for entry in data.get("patterns", []):
        if not isinstance(entry, dict):
            continue
        name = entry.get("id") or entry.get("description") or "rule"
        regex = entry.get("regex", "")
        rules.append(
            ScrubberRule(
                name=str(name),
                pattern=str(regex),
                replacement="<REDACTED>",
            )
        )
    return rules
