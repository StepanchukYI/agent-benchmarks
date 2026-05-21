from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["auth"])

_NOT_IMPLEMENTED = {"detail": "OAuth not implemented (Phase 1 row 7)"}


def _stub() -> JSONResponse:
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/auth/github/login")
def github_login() -> JSONResponse:
    return _stub()


@router.get("/auth/github/callback")
def github_callback() -> JSONResponse:
    return _stub()


@router.get("/me")
def me() -> JSONResponse:
    return _stub()
