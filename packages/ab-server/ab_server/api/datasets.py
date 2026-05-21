from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["datasets"])

_NOT_IMPLEMENTED = {"detail": "Datasets endpoints not implemented yet (Phase 1)"}


def _stub() -> JSONResponse:
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/tasks")
def list_tasks() -> JSONResponse:
    return _stub()


@router.get("/tasks/{id}")
def get_task(id: str) -> JSONResponse:
    return _stub()


@router.get("/tiers")
def list_tiers() -> JSONResponse:
    return _stub()
