from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["repos"])

_NOT_IMPLEMENTED = {"detail": "Repos CRUD not implemented yet (Phase 1 row 8)"}


def _stub() -> JSONResponse:
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.post("/repos")
def register_repo() -> JSONResponse:
    return _stub()


@router.get("/repos")
def list_repos() -> JSONResponse:
    return _stub()


@router.delete("/repos/{id}")
def delete_repo(id: str) -> JSONResponse:
    return _stub()


@router.post("/repos/{id}/sync")
def sync_repo(id: str) -> JSONResponse:
    return _stub()
