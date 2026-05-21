from __future__ import annotations

from ab_server.config import Settings
from ab_server.main import _parse_origins, create_app
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


def _cors_middleware_origins(app) -> list[str] | None:
    for entry in app.user_middleware:
        if entry.cls is CORSMiddleware:
            # Starlette stores keyword args either on .options (older) or .kwargs.
            options = getattr(entry, "kwargs", None) or getattr(entry, "options", {})
            return options.get("allow_origins")
    return None


def test_default_origins_preserve_localhost() -> None:
    app = create_app(Settings(allowed_origins="http://localhost:5173"))
    assert _cors_middleware_origins(app) == ["http://localhost:5173"]


def test_origins_parsed_from_comma_separated_env() -> None:
    settings = Settings(
        allowed_origins="https://a.example.com, https://b.example.com ,https://c.example.com"
    )
    app = create_app(settings)
    assert _cors_middleware_origins(app) == [
        "https://a.example.com",
        "https://b.example.com",
        "https://c.example.com",
    ]


def test_parse_origins_strips_empties() -> None:
    assert _parse_origins(" , https://x.example.com, ") == ["https://x.example.com"]


def test_cors_header_reflects_configured_origin() -> None:
    settings = Settings(
        allowed_origins="https://prod.example.com",
        rate_limit_per_minute=0,
    )
    app = create_app(settings)
    client = TestClient(app)
    response = client.get("/healthz", headers={"Origin": "https://prod.example.com"})
    assert response.status_code == 200
    assert response.headers.get("access-control-allow-origin") == "https://prod.example.com"
