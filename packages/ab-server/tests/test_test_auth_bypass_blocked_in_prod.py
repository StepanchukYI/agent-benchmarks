"""C2 regression: AB_TEST_AUTH=1 must never coexist with IS_PRODUCTION=1.

The test-auth bypass in get_current_user trusts the X-Test-User header and
mints a user with no credentials. That path must be physically unreachable
in production. create_app() refuses to construct the FastAPI app when both
flags are on.
"""

from __future__ import annotations

import pytest
from ab_server.config import Settings
from ab_server.main import create_app


def test_create_app_raises_when_test_auth_enabled_in_production() -> None:
    settings = Settings(ab_test_auth=True, is_production=True)
    with pytest.raises(RuntimeError) as exc_info:
        create_app(settings=settings)
    assert "AB_TEST_AUTH" in str(exc_info.value)
    assert "IS_PRODUCTION" in str(exc_info.value)


def test_create_app_allows_test_auth_outside_production() -> None:
    settings = Settings(ab_test_auth=True, is_production=False)
    # Must not raise: dev/test environments are free to enable the bypass.
    app = create_app(settings=settings)
    assert app is not None


def test_create_app_allows_production_without_test_auth() -> None:
    settings = Settings(ab_test_auth=False, is_production=True)
    # Must not raise: a real production boot is fine, just not with bypass on.
    app = create_app(settings=settings)
    assert app is not None
