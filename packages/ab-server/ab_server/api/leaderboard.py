from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["leaderboard"])

_NOT_IMPLEMENTED = {"detail": "Leaderboard endpoints not implemented yet (Phase 1)"}


def _stub() -> JSONResponse:
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/leaderboard")
def get_leaderboard() -> JSONResponse:
    return _stub()


@router.get("/trends")
def get_trends() -> JSONResponse:
    return _stub()


@router.get("/leaderboard/pareto")
def get_pareto() -> JSONResponse:
    return _stub()
