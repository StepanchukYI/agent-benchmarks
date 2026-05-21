"""In-memory per-IP rate limiting (token bucket).

Single-instance only — homelab behind Caddy/nginx. Multi-instance
deployments would need a shared store (e.g. Redis); explicitly out of scope.

The bucket holds ``rate_limit_per_minute`` tokens and refills linearly at
``rate_limit_per_minute / 60.0`` tokens per second. Each request costs one
token; rejected requests return 429 with ``Retry-After`` set to the seconds
until the bucket has at least one token again.

``/healthz`` is exempt — Docker/Caddy poll it frequently.
"""

from __future__ import annotations

import math
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.types import ASGIApp

# Paths that bypass rate limiting. Keep tiny — only true health probes.
_EXEMPT_PATHS = frozenset({"/healthz"})

# Cap on the number of per-IP buckets retained in memory. Without a cap, a
# botnet that hits us from many unique IPs would grow the dict without bound
# and eventually OOM the process. With LRU eviction the worst case is
# bounded to ``DEFAULT_MAX_BUCKETS`` entries and the oldest unseen IPs lose
# their bucket state first.
DEFAULT_MAX_BUCKETS = 10_000


@dataclass
class _Bucket:
    tokens: float
    last_refill: float


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Token-bucket per-IP rate limiter with LRU bucket eviction."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        per_minute: int,
        max_buckets: int = DEFAULT_MAX_BUCKETS,
    ) -> None:
        super().__init__(app)
        if per_minute <= 0:
            raise ValueError("RateLimitMiddleware requires per_minute > 0")
        if max_buckets <= 0:
            raise ValueError("RateLimitMiddleware requires max_buckets > 0")
        self._per_minute = per_minute
        self._capacity = float(per_minute)
        self._refill_per_sec = per_minute / 60.0
        self._max_buckets = max_buckets
        # OrderedDict gives O(1) move-to-end + popitem(last=False), so we can
        # treat insertion order as recency order and evict the LRU bucket
        # whenever the dict grows past ``max_buckets``.
        self._buckets: OrderedDict[str, _Bucket] = OrderedDict()
        self._lock = threading.Lock()

    def _client_key(self, request: Request) -> str:
        # ``request.client`` is None for test transports without a peer;
        # fall back to a constant key so the limiter is still testable.
        client = request.client
        if client is None or not client.host:
            return "unknown"
        return client.host

    def _consume(self, key: str) -> tuple[bool, float]:
        """Return (allowed, retry_after_sec). retry_after_sec is 0 when allowed."""
        now = time.monotonic()
        with self._lock:
            bucket = self._buckets.get(key)
            if bucket is None:
                bucket = _Bucket(tokens=self._capacity, last_refill=now)
                self._buckets[key] = bucket
            else:
                elapsed = now - bucket.last_refill
                if elapsed > 0:
                    bucket.tokens = min(
                        self._capacity, bucket.tokens + elapsed * self._refill_per_sec
                    )
                    bucket.last_refill = now
                # Mark this key as most-recently-used so it survives the
                # next eviction pass.
                self._buckets.move_to_end(key)

            # Evict oldest entries until we're at or below the cap. Runs
            # after every access so a sudden burst of unique IPs cannot
            # push the dict significantly above ``max_buckets``.
            while len(self._buckets) > self._max_buckets:
                self._buckets.popitem(last=False)

            if bucket.tokens >= 1.0:
                bucket.tokens -= 1.0
                return True, 0.0

            needed = 1.0 - bucket.tokens
            retry_after = needed / self._refill_per_sec if self._refill_per_sec else 60.0
            return False, retry_after

    async def dispatch(self, request: Request, call_next):  # type: ignore[override]
        # CORS preflight (OPTIONS) is cheap and is sent by browsers ahead of
        # most cross-origin requests. Counting it against the budget burns the
        # bucket on legitimate clients, and a bare 429 has no CORS headers, so
        # the browser sees an opaque failure rather than a usable error.
        # Exempt OPTIONS entirely.
        if request.method == "OPTIONS":
            return await call_next(request)

        if request.url.path in _EXEMPT_PATHS:
            return await call_next(request)

        allowed, retry_after = self._consume(self._client_key(request))
        if allowed:
            return await call_next(request)

        retry_seconds = max(1, math.ceil(retry_after))
        return _rate_limited_response(retry_seconds)


def _rate_limited_response(retry_after: int) -> Response:
    return JSONResponse(
        status_code=429,
        content={"error": "rate_limited", "retry_after_sec": retry_after},
        headers={"Retry-After": str(retry_after)},
    )
