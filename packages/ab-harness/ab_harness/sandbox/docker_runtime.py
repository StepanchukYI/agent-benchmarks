"""Container-backed sandbox runtime (P4.18).

Provides ``DockerRuntime`` for running an agent (or any command) inside an
isolated container with a read-write bind-mounted workdir. Complements
``ab_harness.sandbox.docker.materialize``, which prepares the workdir on
the host but executes the runner outside any container.

Why a runtime layer at all:

* Workdir lives entirely on the host today. A misbehaving agent that escapes
  the sandbox prompt (see B6/B7 in the May 21 review) can navigate the host
  fs freely. Containerised execution closes that escape — the container only
  sees the mounted workdir and an empty ``/tmp``.
* Network isolation. Default ``network="none"`` so a runner can't exfiltrate.
  Override to ``"bridge"`` for runners that legitimately need GitHub /
  package-registry access during the run.
* Resource caps. Memory + CPU + pids limits stop a runaway agent from
  eating the homelab.
* Reproducibility. Same image SHA across runs → same toolchain.

Not in scope here:

* Pulling skills / MCP configs into the container. ``docker.materialize``
  already lays down ``CLAUDE.md`` + ``.claude/SKILLS.txt`` + the vault
  snapshot in the workdir; the runtime just mounts that workdir.
* Multi-step exec inside one container. The runtime is single-shot:
  ``run(cmd)`` starts a container, runs ``cmd``, captures stdout/stderr/
  exit, removes the container. Use the higher-level runner pattern
  (one container per benchmark task) rather than long-lived shells.

Use as a context manager so the container is always removed::

    with DockerRuntime(image="python:3.11-slim", workdir=workdir) as rt:
        result = rt.run(["python", "-c", "print('hello')"])
        assert result.exit_code == 0
"""

from __future__ import annotations

import contextlib
import logging
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping


_log = logging.getLogger(__name__)

# ``/workdir`` is the canonical mount point inside the container. Agents see
# it as cwd; the host workdir is bound here read-write.
_CONTAINER_WORKDIR = "/workdir"

# Default resource caps. Tuned for benchmark scoring runs (CPU-bound, small
# memory). Override per-runtime via the ``resources`` kwarg.
_DEFAULT_MEM_LIMIT = "1g"
_DEFAULT_CPU_QUOTA = 100_000  # 1 CPU at 100k microseconds period
_DEFAULT_PIDS_LIMIT = 512
_DEFAULT_TIMEOUT_SEC = 600


class DockerRuntimeError(RuntimeError):
    """Container failed to start / exec / cleanup."""


@dataclass(frozen=True)
class DockerResources:
    """Resource caps applied to every container started by the runtime."""

    mem_limit: str = _DEFAULT_MEM_LIMIT
    cpu_quota: int = _DEFAULT_CPU_QUOTA
    cpu_period: int = 100_000
    pids_limit: int = _DEFAULT_PIDS_LIMIT
    tmpfs_size: str = "256m"


@dataclass(frozen=True)
class DockerExecResult:
    """What ``DockerRuntime.run`` returns."""

    command: tuple[str, ...]
    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool

    @property
    def ok(self) -> bool:
        return self.exit_code == 0 and not self.timed_out


class DockerRuntime:
    """Run a single command in a fresh, locked-down container.

    Lifecycle:

    1. ``__init__`` validates inputs but does not touch Docker.
    2. ``__enter__`` (or ``ensure_image()``) pulls the image if missing.
    3. ``run(cmd, *, timeout=None)`` starts the container, runs ``cmd``,
       captures output, removes the container. Safe to call multiple times
       — each call is a fresh container.
    4. ``__exit__`` is a no-op other than logging (no long-lived state).

    The ``workdir`` is bind-mounted read-write so the agent can produce
    files; the host sees them after ``run`` returns.
    """

    def __init__(
        self,
        *,
        image: str,
        workdir: Path,
        env: Mapping[str, str] | None = None,
        network: str = "none",
        user: str | None = None,
        read_only_rootfs: bool = True,
        resources: DockerResources | None = None,
        default_timeout_sec: int = _DEFAULT_TIMEOUT_SEC,
        docker_client: Any = None,
        extra_mounts: Iterable[tuple[Path, str, bool]] | None = None,
    ) -> None:
        if not image:
            raise DockerRuntimeError("image required")
        workdir = Path(workdir)
        if not workdir.exists():
            raise DockerRuntimeError(f"workdir does not exist: {workdir}")
        if not workdir.is_dir():
            raise DockerRuntimeError(f"workdir is not a directory: {workdir}")

        self._image = image
        self._workdir = workdir.resolve()
        self._env = dict(env or {})
        self._network = network
        self._user = user
        self._read_only_rootfs = read_only_rootfs
        self._resources = resources or DockerResources()
        self._default_timeout_sec = default_timeout_sec
        self._docker_client = docker_client
        # extra_mounts: each entry is (host_path, container_path, read_only)
        self._extra_mounts = list(extra_mounts or [])

    @property
    def image(self) -> str:
        return self._image

    @property
    def workdir(self) -> Path:
        return self._workdir

    def __enter__(self) -> DockerRuntime:
        self.ensure_image()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        # Each ``run`` cleans up its own container; nothing left to do.
        if exc is not None:
            _log.debug("DockerRuntime exiting with exception: %r", exc)

    # ------------------------------------------------------------------
    # Docker client glue
    # ------------------------------------------------------------------

    def _client(self) -> Any:
        if self._docker_client is not None:
            return self._docker_client
        try:
            import docker  # type: ignore[import-not-found]
        except ImportError as exc:
            raise DockerRuntimeError(
                "docker SDK not installed; add 'docker' to dependencies"
            ) from exc
        try:
            self._docker_client = docker.from_env()
        except Exception as exc:
            raise DockerRuntimeError(f"docker daemon unreachable: {exc}") from exc
        return self._docker_client

    def ensure_image(self) -> None:
        """Pull the image if missing. Idempotent."""
        client = self._client()
        try:
            client.images.get(self._image)
            return
        except Exception:
            # Most likely ImageNotFound — fall through to pull.
            pass
        _log.info("docker pull %s", self._image)
        try:
            client.images.pull(self._image)
        except Exception as exc:
            raise DockerRuntimeError(
                f"failed to pull image {self._image!r}: {exc}"
            ) from exc

    # ------------------------------------------------------------------
    # Run
    # ------------------------------------------------------------------

    def run(
        self,
        command: list[str] | str,
        *,
        timeout: int | None = None,
        env_overrides: Mapping[str, str] | None = None,
    ) -> DockerExecResult:
        """Run ``command`` in a fresh container; return captured output.

        ``command`` may be a list (preferred — no shell interpolation) or a
        string (split via shlex; useful for tests). ``timeout`` defaults to
        the runtime's ``default_timeout_sec``.
        """
        client = self._client()
        cmd_list = (
            list(command) if isinstance(command, list) else shlex.split(command)
        )
        if not cmd_list:
            raise DockerRuntimeError("command must be non-empty")

        timeout_sec = timeout if timeout is not None else self._default_timeout_sec
        merged_env = {**self._env, **(env_overrides or {})}

        volumes: dict[str, dict[str, str]] = {
            str(self._workdir): {"bind": _CONTAINER_WORKDIR, "mode": "rw"},
        }
        for host_path, container_path, read_only in self._extra_mounts:
            volumes[str(Path(host_path).resolve())] = {
                "bind": container_path,
                "mode": "ro" if read_only else "rw",
            }

        host_config: dict[str, Any] = {
            "mem_limit": self._resources.mem_limit,
            "cpu_period": self._resources.cpu_period,
            "cpu_quota": self._resources.cpu_quota,
            "pids_limit": self._resources.pids_limit,
            "read_only": self._read_only_rootfs,
            "network_mode": self._network,
            "tmpfs": {"/tmp": f"size={self._resources.tmpfs_size}"},
            # Drop everything except basic. Net is already "none" by default
            # so most caps would be meaningless; defense in depth.
            "cap_drop": ["ALL"],
            "security_opt": ["no-new-privileges"],
        }

        timed_out = False
        container = None
        try:
            container = client.containers.create(
                self._image,
                command=cmd_list,
                working_dir=_CONTAINER_WORKDIR,
                environment=merged_env or None,
                user=self._user,
                volumes=volumes,
                detach=True,
                **host_config,
            )
            container.start()
            try:
                result = container.wait(timeout=timeout_sec)
                exit_code = int(result.get("StatusCode", -1))
            except Exception as exc:
                # docker.errors.ReadTimeoutError / requests timeout / etc.
                # All mean the container is still running. Kill it.
                _log.warning(
                    "container %s timed out after %ds: %s",
                    getattr(container, "id", "?"),
                    timeout_sec,
                    exc,
                )
                timed_out = True
                exit_code = -1
                with contextlib.suppress(Exception):
                    container.kill()

            try:
                stdout = container.logs(stdout=True, stderr=False).decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                stdout = ""
            try:
                stderr = container.logs(stdout=False, stderr=True).decode(
                    "utf-8", errors="replace"
                )
            except Exception:
                stderr = ""

            return DockerExecResult(
                command=tuple(cmd_list),
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                timed_out=timed_out,
            )
        finally:
            if container is not None:
                try:
                    container.remove(force=True)
                except Exception as exc:
                    _log.warning(
                        "failed to remove container %s: %s",
                        getattr(container, "id", "?"),
                        exc,
                    )


__all__ = [
    "DockerExecResult",
    "DockerResources",
    "DockerRuntime",
    "DockerRuntimeError",
]
