from __future__ import annotations

from ab_server.main import app
from fastapi.testclient import TestClient


def test_list_tiers_returns_t0_through_t3() -> None:
    client = TestClient(app)
    resp = client.get("/api/v1/tiers")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    names = {item["name"] for item in body["items"]}
    assert {"T0", "T1", "T2", "T3"}.issubset(names)
    by_name = {item["name"]: item for item in body["items"]}
    # T0 has no CLAUDE.md
    assert by_name["T0"]["claude_md_present"] is False
    assert by_name["T0"]["skills_count"] == 0
    # T1 has CLAUDE.md but no skills
    assert by_name["T1"]["claude_md_present"] is True
    # T2 has CLAUDE.md, skills, mcps and vault snapshot
    assert by_name["T2"]["claude_md_present"] is True
    assert by_name["T2"]["skills_count"] >= 2
    assert by_name["T2"]["mcps_count"] >= 1
    assert by_name["T2"]["vault_snapshot"] is not None
