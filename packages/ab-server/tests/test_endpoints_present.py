from __future__ import annotations

from ab_server.main import app

# (method, path) pairs from Build Spec §10. /healthz is mounted at the root,
# everything else under /api/v1.
EXPECTED_ENDPOINTS: list[tuple[str, str]] = [
    ("GET", "/healthz"),
    ("GET", "/api/v1/version"),
    ("GET", "/api/v1/auth/github/login"),
    ("GET", "/api/v1/auth/github/callback"),
    ("GET", "/api/v1/me"),
    ("POST", "/api/v1/repos"),
    ("GET", "/api/v1/repos"),
    ("DELETE", "/api/v1/repos/{id}"),
    ("POST", "/api/v1/repos/{id}/sync"),
    ("POST", "/api/v1/runs"),
    ("GET", "/api/v1/runs"),
    ("GET", "/api/v1/runs/{id}"),
    ("GET", "/api/v1/runs/{id}/stream"),
    ("GET", "/api/v1/runs/{id}/trajectories/{task_id}"),
    ("GET", "/api/v1/submissions"),
    ("GET", "/api/v1/submissions/{id}"),
    ("GET", "/api/v1/tasks"),
    ("GET", "/api/v1/tasks/{id}"),
    ("GET", "/api/v1/tiers"),
    ("GET", "/api/v1/leaderboard"),
    ("GET", "/api/v1/trends"),
    ("GET", "/api/v1/leaderboard/pareto"),
]


def _registered_endpoints() -> set[tuple[str, str]]:
    schema = app.openapi()
    pairs: set[tuple[str, str]] = set()
    for path, ops in schema.get("paths", {}).items():
        for method in ops:
            pairs.add((method.upper(), path))
    return pairs


def test_all_spec_endpoints_registered() -> None:
    registered = _registered_endpoints()
    missing = [item for item in EXPECTED_ENDPOINTS if item not in registered]
    assert not missing, f"Missing endpoints in OpenAPI: {missing}"
