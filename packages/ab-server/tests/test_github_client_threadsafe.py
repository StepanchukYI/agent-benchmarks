"""Thread-safety of the lazy ``_GH_CLIENT`` singleton.

Under gunicorn with threaded workers (or any concurrent caller), a naive
``if _GH_CLIENT is None: _GH_CLIENT = httpx.Client(...)`` pattern can race:
two threads both see None, each construct a client, and one is silently
discarded — leaking the underlying file descriptors / connection pool.

We assert the double-checked-locking pattern by spawning many threads that
all call ``get_github_client()`` simultaneously and confirming they all
receive the same object identity.
"""

from __future__ import annotations

import threading
from collections.abc import Iterator

import httpx
import pytest
from ab_server.auth import github_oauth
from ab_server.auth.github_oauth import get_github_client, reset_github_client


@pytest.fixture(autouse=True)
def _clean_singleton() -> Iterator[None]:
    """Each test starts with a fresh singleton state."""
    reset_github_client()
    try:
        yield
    finally:
        reset_github_client()


def test_concurrent_get_returns_single_instance() -> None:
    """10 threads racing get_github_client() must all observe the same client."""
    threads_count = 10
    results: list[httpx.Client] = []
    results_lock = threading.Lock()
    start_barrier = threading.Barrier(threads_count)

    def worker() -> None:
        # Force every thread to leave the barrier at (nearly) the same instant
        # so the race window is maximised. Without this, the threads serialise
        # naturally and the bug is invisible.
        start_barrier.wait()
        client = get_github_client()
        with results_lock:
            results.append(client)

    threads = [threading.Thread(target=worker) for _ in range(threads_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == threads_count
    first = results[0]
    assert all(client is first for client in results), (
        "Multiple distinct httpx.Client instances created — lock missing or wrong."
    )


def test_lock_exists_at_module_level() -> None:
    """Sanity: the module exposes a Lock used to guard the singleton."""
    assert hasattr(github_oauth, "_LOCK"), "_LOCK missing from github_oauth"
    # Lock primitive isn't a public class, but its repr starts with '<locked '/'<unlocked '
    # and it must support context-manager semantics.
    lock = github_oauth._LOCK
    with lock:
        pass


def test_reset_then_get_creates_new_instance() -> None:
    """After reset, a fresh client is created (and shared by concurrent callers)."""
    first = get_github_client()
    reset_github_client()
    second = get_github_client()
    assert second is not first

    # And concurrent callers after the second creation still share it.
    threads_count = 8
    results: list[httpx.Client] = []
    results_lock = threading.Lock()
    barrier = threading.Barrier(threads_count)

    def worker() -> None:
        barrier.wait()
        with results_lock:
            results.append(get_github_client())

    threads = [threading.Thread(target=worker) for _ in range(threads_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert all(client is second for client in results)
