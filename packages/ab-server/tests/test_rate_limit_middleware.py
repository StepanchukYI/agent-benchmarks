from __future__ import annotations

from ab_server.config import Settings
from ab_server.main import create_app
from fastapi.testclient import TestClient

# Settings() reads the environment; tests pass values explicitly to avoid env bleed.


def test_burst_over_limit_returns_429() -> None:
    settings = Settings(rate_limit_per_minute=120)
    app = create_app(settings)
    client = TestClient(app)

    # Hit a real (non-exempt) endpoint 121 times back-to-back.
    last_status = None
    for _ in range(121):
        last_status = client.get("/api/v1/version").status_code

    assert last_status == 429


def test_429_body_and_retry_after_header() -> None:
    settings = Settings(rate_limit_per_minute=2)
    app = create_app(settings)
    client = TestClient(app)

    # Drain the bucket.
    for _ in range(2):
        client.get("/api/v1/version")
    response = client.get("/api/v1/version")
    assert response.status_code == 429
    body = response.json()
    assert body == {"error": "rate_limited", "retry_after_sec": body["retry_after_sec"]}
    assert body["retry_after_sec"] >= 1
    assert response.headers["Retry-After"] == str(body["retry_after_sec"])


def test_healthz_is_exempt_from_rate_limit() -> None:
    settings = Settings(rate_limit_per_minute=5)
    app = create_app(settings)
    client = TestClient(app)

    # Way more than the limit — every one must succeed.
    for _ in range(50):
        response = client.get("/healthz")
        assert response.status_code == 200


def test_rate_limit_disabled_when_zero() -> None:
    settings = Settings(rate_limit_per_minute=0)
    app = create_app(settings)

    from ab_server.middleware.rate_limit import RateLimitMiddleware

    assert all(entry.cls is not RateLimitMiddleware for entry in app.user_middleware)

    client = TestClient(app)
    for _ in range(150):
        assert client.get("/api/v1/version").status_code == 200
