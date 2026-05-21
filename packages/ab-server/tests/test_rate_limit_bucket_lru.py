"""H7: bucket dict must not grow unbounded; LRU eviction caps it.

We hammer the middleware's `_consume` directly with synthetic IPs. The
TestClient transport doesn't let us forge arbitrary `request.client.host`,
and we don't need a real HTTP path to exercise the eviction logic — the
dict is keyed by the string the middleware computes from the request.
"""
from __future__ import annotations

import threading

from ab_server.middleware.rate_limit import RateLimitMiddleware
from starlette.applications import Starlette


def _make_middleware(max_buckets: int) -> RateLimitMiddleware:
    # The Starlette app inside is irrelevant; we drive _consume directly.
    inner = Starlette()
    return RateLimitMiddleware(inner, per_minute=120, max_buckets=max_buckets)


def test_bucket_dict_bounded_under_many_unique_ips() -> None:
    """10_001 unique IPs must not push dict past max_buckets."""
    mw = _make_middleware(max_buckets=10_000)
    for i in range(10_001):
        allowed, _ = mw._consume(f"10.0.{i // 256}.{i % 256}")
        assert allowed is True
    assert len(mw._buckets) == 10_000


def test_oldest_keys_evicted_first() -> None:
    """LRU semantics: the FIRST-seen keys disappear after we overflow."""
    mw = _make_middleware(max_buckets=3)
    for key in ("a", "b", "c"):
        mw._consume(key)
    # All three present.
    assert set(mw._buckets.keys()) == {"a", "b", "c"}
    # Touch 'a' so it becomes most-recently-used.
    mw._consume("a")
    # Add a fourth. 'b' (oldest untouched) should be evicted, not 'a'.
    mw._consume("d")
    assert set(mw._buckets.keys()) == {"a", "c", "d"}


def test_repeated_hits_from_same_ip_dont_evict_others() -> None:
    """A single hot IP shouldn't push out cold ones until the cap is reached."""
    mw = _make_middleware(max_buckets=5)
    for key in ("a", "b", "c", "d", "e"):
        mw._consume(key)
    # 200 hits on "a" only refill/decrement that bucket; dict size is stable.
    for _ in range(200):
        mw._consume("a")
    assert len(mw._buckets) == 5
    assert set(mw._buckets.keys()) == {"a", "b", "c", "d", "e"}


def test_eviction_is_thread_safe() -> None:
    """Concurrent consumers across many IPs must keep size within the cap."""
    mw = _make_middleware(max_buckets=50)

    def worker(start: int) -> None:
        for i in range(start, start + 500):
            mw._consume(f"client-{i}")

    threads = [threading.Thread(target=worker, args=(i * 500,)) for i in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(mw._buckets) <= 50


def test_default_max_buckets_is_ten_thousand() -> None:
    """Sanity check that the documented default doesn't drift silently."""
    inner = Starlette()
    mw = RateLimitMiddleware(inner, per_minute=120)
    assert mw._max_buckets == 10_000


def test_rejects_invalid_max_buckets() -> None:
    inner = Starlette()
    import pytest

    with pytest.raises(ValueError):
        RateLimitMiddleware(inner, per_minute=120, max_buckets=0)
    with pytest.raises(ValueError):
        RateLimitMiddleware(inner, per_minute=120, max_buckets=-1)
