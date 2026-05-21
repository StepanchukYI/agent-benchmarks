from __future__ import annotations

from fastapi import APIRouter

from ab_server import __version__

try:
    from ab_datasets import __version__ as ab_datasets_version
except Exception:  # pragma: no cover - dataset package may be missing in early scaffolding
    ab_datasets_version = "unknown"

# Liveness — mounted at app root, NOT under /api/v1.
health_router = APIRouter(tags=["system"])


@health_router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


# Version — mounted under /api/v1.
v1_router = APIRouter(tags=["system"])


@v1_router.get("/version")
def version() -> dict[str, str]:
    return {"server": __version__, "ab_datasets": ab_datasets_version}
