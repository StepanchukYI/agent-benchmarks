"""Top-level pytest conftest — sets test-environment defaults BEFORE
any test module (and therefore any `from ab_server.main import app`)
gets imported.

Tests share a module-level FastAPI `app` instance with a shared
in-memory rate-limit bucket. Production rate limit (120/min) drains
quickly under a 400+ test suite, causing unrelated tests downstream to
get 429s. Disable rate limiting by default in tests; specific tests
that exercise the rate limiter create their own `app` with explicit
settings.
"""

from __future__ import annotations

import os

os.environ.setdefault("RATE_LIMIT_PER_MINUTE", "0")
