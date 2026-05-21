from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ab_server import __version__
from ab_server.api import v1_routers
from ab_server.api.system import health_router


def create_app() -> FastAPI:
    app = FastAPI(
        title="agent-benchmarks",
        version=__version__,
        description=(
            "Server API for agent-benchmarks. Phase 0 skeleton: only /healthz "
            "and /api/v1/version are live. All other endpoints from Build Spec "
            "§10 return 501 with an explanatory body."
        ),
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health_router)
    for router in v1_routers:
        app.include_router(router, prefix="/api/v1")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("ab_server.main:app", host="0.0.0.0", port=8000)
