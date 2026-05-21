from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ab_server import __version__
from ab_server.api import v1_routers
from ab_server.api.system import health_router
from ab_server.config import Settings
from ab_server.logging_setup import configure_logging
from ab_server.middleware.rate_limit import RateLimitMiddleware


def _parse_origins(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def create_app(settings: Settings | None = None) -> FastAPI:
    if settings is None:
        settings = Settings()

    configure_logging(log_format=settings.log_format)

    app = FastAPI(
        title="agent-benchmarks",
        version=__version__,
        description=(
            "Server API for agent-benchmarks. Phase 0 skeleton: only /healthz "
            "and /api/v1/version are live. All other endpoints from Build Spec "
            "§10 return 501 with an explanatory body."
        ),
    )

    # Middleware registration order is the REVERSE of execution order in
    # Starlette: the last add_middleware call wraps outermost. We want
    # requests to flow: ProxyHeaders -> RateLimit -> CORS -> routes,
    # so we add CORS first, then RateLimit, then ProxyHeaders.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_parse_origins(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if settings.rate_limit_per_minute > 0:
        app.add_middleware(
            RateLimitMiddleware,
            per_minute=settings.rate_limit_per_minute,
        )

    if settings.ab_trust_proxy:
        # Comes with uvicorn[standard]. Rewrites request.client.host and
        # request.url.scheme from X-Forwarded-For / X-Forwarded-Proto so
        # OAuth callbacks and rate-limit-by-IP work behind nginx/Caddy.
        from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

        app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

    app.include_router(health_router)
    for router in v1_routers:
        app.include_router(router, prefix="/api/v1")

    return app


app = create_app()


def run() -> None:
    import uvicorn

    uvicorn.run("ab_server.main:app", host="0.0.0.0", port=8000)
