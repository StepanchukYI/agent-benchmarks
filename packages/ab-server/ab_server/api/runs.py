from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["runs"])

_NOT_IMPLEMENTED = {"detail": "Runs endpoints not implemented yet (Phase 1)"}


def _stub() -> JSONResponse:
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.post("/runs")
def create_run() -> JSONResponse:
    return _stub()


@router.get("/runs")
def list_runs() -> JSONResponse:
    return _stub()


@router.get("/runs/{id}")
def get_run(id: str) -> JSONResponse:
    return _stub()


@router.get("/runs/{id}/stream")
def stream_run(id: str) -> JSONResponse:
    return _stub()


@router.get("/runs/{id}/trajectories/{task_id}")
def get_trajectory(id: str, task_id: str) -> JSONResponse:
    return _stub()
