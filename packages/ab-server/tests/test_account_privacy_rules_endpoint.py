from __future__ import annotations

from ab_server.main import app
from fastapi.testclient import TestClient


def test_privacy_rules_endpoint_returns_patterns() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/account/privacy-rules")
    assert resp.status_code == 200, resp.text
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) >= 1
    sample = items[0]
    assert {"name", "pattern", "replacement"}.issubset(sample.keys())
    assert sample["replacement"] == "<REDACTED>"

    names = {item["name"] for item in items}
    assert any("email" in n for n in names)
