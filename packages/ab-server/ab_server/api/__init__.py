from __future__ import annotations

from fastapi import APIRouter

from ab_server.api import (
    account,
    alerts,
    auth,
    catalog,
    datasets,
    jobs,
    leaderboard,
    presets,
    repos,
    runs,
    submissions,
    system,
)

# Routers mounted under /api/v1 by main.py (except system.health which is at root).
v1_routers: list[APIRouter] = [
    system.v1_router,
    auth.router,
    repos.router,
    runs.router,
    submissions.router,
    datasets.router,
    leaderboard.router,
    presets.router,
    alerts.router,
    catalog.router,
    account.router,
    jobs.router,
]

__all__ = ["system", "v1_routers"]
