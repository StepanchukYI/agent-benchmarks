from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter(tags=["submissions"])

_NOT_IMPLEMENTED = {"detail": "Submissions endpoints not implemented yet (Phase 1)"}


def _stub() -> JSONResponse:
    return JSONResponse(status_code=501, content=_NOT_IMPLEMENTED)


@router.get("/submissions")
def list_submissions() -> JSONResponse:
    return _stub()


@router.get("/submissions/{id}")
def get_submission(id: str) -> JSONResponse:
    return _stub()
