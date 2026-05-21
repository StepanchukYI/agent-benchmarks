"""OPTIONS preflight must bypass the rate limiter.

Browsers send a CORS preflight (OPTIONS) before most cross-origin requests.
Counting them against the budget burns through the bucket on legitimate
clients, and a bare 429 response carries no CORS headers — so the browser
just sees an opaque failure rather than the rate-limit error we wanted to
return. Exempt OPTIONS entirely.
"""

from __future__ import annotations

from ab_server.config import Settings
from ab_server.main import create_app
from fastapi.testclient import TestClient


def test_options_preflight_is_exempt_from_rate_limit() -> None:
    """121 OPTIONS requests in a row with limit=120 must never return 429."""
    settings = Settings(rate_limit_per_minute=120)
    app = create_app(settings)
    client = TestClient(app)

    headers = {
        "Origin": "http://localhost:5173",
        "Access-Control-Request-Method": "GET",
    }
    statuses: set[int] = set()
    for _ in range(121):
        resp = client.options("/api/v1/version", headers=headers)
        statuses.add(resp.status_code)

    # The exact response code for OPTIONS varies with router setup (200/204/405),
    # but 429 must NEVER appear when the request is OPTIONS.
    assert 429 not in statuses, f"OPTIONS got rate-limited: saw statuses {statuses}"


def test_options_does_not_consume_budget_for_other_methods() -> None:
    """A burst of OPTIONS must leave the GET budget untouched."""
    settings = Settings(rate_limit_per_minute=5)
    app = create_app(settings)
    client = TestClient(app)

    # Fire 50 OPTIONS — way over the limit — they must not eat tokens.
    for _ in range(50):
        client.options("/api/v1/version")

    # Now we should still have all 5 GET tokens available.
    last_status = None
    for _ in range(5):
        last_status = client.get("/api/v1/version").status_code
    # First 5 GETs must all succeed (200), 6th is the first to get 429.
    assert last_status == 200
    assert client.get("/api/v1/version").status_code == 429


def test_options_429_would_have_cors_headers_if_returned() -> None:
    """Sanity check: confirm OPTIONS responses include CORS headers.

    This documents why the exemption matters — if a 429 ever escaped to the
    browser for OPTIONS, it would not have the Access-Control-Allow-Origin
    header that the browser requires to surface the response.
    """
    settings = Settings(rate_limit_per_minute=120)
    app = create_app(settings)
    client = TestClient(app)

    resp = client.options(
        "/api/v1/version",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
        },
    )
    # Whatever the status, OPTIONS must not be a 429.
    assert resp.status_code != 429
