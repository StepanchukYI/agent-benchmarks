"""DockerRuntime — single-shot container exec with locked-down defaults.

All tests use a mock docker client; no real Docker required in CI.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from ab_harness.sandbox.docker_runtime import (
    DockerExecResult,
    DockerResources,
    DockerRuntime,
    DockerRuntimeError,
)

# ---------------------------------------------------------------------------
# Fake docker client
# ---------------------------------------------------------------------------


class _FakeContainer:
    def __init__(
        self,
        *,
        exit_code: int = 0,
        stdout: bytes = b"",
        stderr: bytes = b"",
        timeout_exc: Exception | None = None,
    ) -> None:
        self.id = "fake-container-id"
        self._exit_code = exit_code
        self._stdout = stdout
        self._stderr = stderr
        self._timeout_exc = timeout_exc
        self.started = False
        self.killed = False
        self.removed = False
        self.start_call_args: dict[str, Any] = {}

    def start(self) -> None:
        self.started = True

    def wait(self, *, timeout: int) -> dict[str, int]:
        if self._timeout_exc is not None:
            raise self._timeout_exc
        return {"StatusCode": self._exit_code}

    def kill(self) -> None:
        self.killed = True

    def remove(self, *, force: bool) -> None:
        self.removed = True

    def logs(self, *, stdout: bool, stderr: bool) -> bytes:
        if stdout and not stderr:
            return self._stdout
        if stderr and not stdout:
            return self._stderr
        return b""


class _FakeImages:
    def __init__(self, *, has_image: bool = True, pull_raises: Exception | None = None) -> None:
        self._has_image = has_image
        self._pull_raises = pull_raises
        self.pulled: list[str] = []

    def get(self, image: str) -> Any:
        if not self._has_image:
            raise RuntimeError(f"ImageNotFound: {image}")
        return MagicMock(id="sha256:abc")

    def pull(self, image: str) -> Any:
        if self._pull_raises is not None:
            raise self._pull_raises
        self.pulled.append(image)
        self._has_image = True


class _FakeContainers:
    def __init__(self, container: _FakeContainer) -> None:
        self._container = container
        self.create_calls: list[dict[str, Any]] = []

    def create(self, image: str, **kwargs: Any) -> _FakeContainer:
        self.create_calls.append({"image": image, **kwargs})
        return self._container


class _FakeClient:
    def __init__(
        self,
        *,
        container: _FakeContainer | None = None,
        images: _FakeImages | None = None,
    ) -> None:
        self.containers = _FakeContainers(container or _FakeContainer())
        self.images = images or _FakeImages()


# ---------------------------------------------------------------------------
# Construction / validation
# ---------------------------------------------------------------------------


def test_init_rejects_missing_workdir(tmp_path: Path) -> None:
    with pytest.raises(DockerRuntimeError, match="workdir does not exist"):
        DockerRuntime(image="alpine", workdir=tmp_path / "missing")


def test_init_rejects_file_as_workdir(tmp_path: Path) -> None:
    f = tmp_path / "file"
    f.write_text("not a dir")
    with pytest.raises(DockerRuntimeError, match="not a directory"):
        DockerRuntime(image="alpine", workdir=f)


def test_init_requires_image(tmp_path: Path) -> None:
    with pytest.raises(DockerRuntimeError, match="image required"):
        DockerRuntime(image="", workdir=tmp_path)


# ---------------------------------------------------------------------------
# ensure_image
# ---------------------------------------------------------------------------


def test_ensure_image_skip_when_present(tmp_path: Path) -> None:
    client = _FakeClient(images=_FakeImages(has_image=True))
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    rt.ensure_image()
    assert client.images.pulled == []


def test_ensure_image_pulls_when_missing(tmp_path: Path) -> None:
    client = _FakeClient(images=_FakeImages(has_image=False))
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    rt.ensure_image()
    assert client.images.pulled == ["alpine"]


def test_ensure_image_pull_failure_raises(tmp_path: Path) -> None:
    client = _FakeClient(
        images=_FakeImages(has_image=False, pull_raises=RuntimeError("rate limit"))
    )
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    with pytest.raises(DockerRuntimeError, match="failed to pull"):
        rt.ensure_image()


# ---------------------------------------------------------------------------
# run
# ---------------------------------------------------------------------------


def test_run_success_returns_captured_output(tmp_path: Path) -> None:
    container = _FakeContainer(
        exit_code=0,
        stdout=b"hello world\n",
        stderr=b"",
    )
    client = _FakeClient(container=container)
    rt = DockerRuntime(
        image="python:3.11-slim",
        workdir=tmp_path,
        docker_client=client,
    )
    result = rt.run(["python", "-c", "print('hello world')"])
    assert isinstance(result, DockerExecResult)
    assert result.exit_code == 0
    assert result.stdout == "hello world\n"
    assert result.stderr == ""
    assert result.timed_out is False
    assert result.ok is True
    assert container.started is True
    assert container.removed is True


def test_run_failure_propagates_exit_code(tmp_path: Path) -> None:
    container = _FakeContainer(
        exit_code=2,
        stdout=b"",
        stderr=b"boom\n",
    )
    client = _FakeClient(container=container)
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    result = rt.run(["sh", "-c", "exit 2"])
    assert result.exit_code == 2
    assert result.stderr == "boom\n"
    assert result.ok is False


def test_run_timeout_kills_container_and_marks_result(tmp_path: Path) -> None:
    container = _FakeContainer(
        exit_code=0,
        stdout=b"partial",
        stderr=b"",
        timeout_exc=TimeoutError("wait timed out"),
    )
    client = _FakeClient(container=container)
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    result = rt.run(["sleep", "9999"], timeout=1)
    assert result.timed_out is True
    assert result.exit_code == -1
    assert container.killed is True
    assert container.removed is True


def test_run_string_command_is_shlex_split(tmp_path: Path) -> None:
    container = _FakeContainer(exit_code=0)
    client = _FakeClient(container=container)
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    rt.run("echo 'hello world'")
    call = client.containers.create_calls[0]
    assert call["command"] == ["echo", "hello world"]


def test_run_empty_command_raises(tmp_path: Path) -> None:
    client = _FakeClient()
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    with pytest.raises(DockerRuntimeError, match="non-empty"):
        rt.run([])


def test_run_passes_locked_down_host_config(tmp_path: Path) -> None:
    """Defaults — read-only rootfs, network none, cap_drop ALL, no-new-privs."""
    container = _FakeContainer(exit_code=0)
    client = _FakeClient(container=container)
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    rt.run(["true"])
    call = client.containers.create_calls[0]
    assert call["network_mode"] == "none"
    assert call["read_only"] is True
    assert call["cap_drop"] == ["ALL"]
    assert "no-new-privileges" in call["security_opt"]
    assert call["pids_limit"] == 512
    assert call["mem_limit"] == "1g"


def test_run_mounts_workdir(tmp_path: Path) -> None:
    container = _FakeContainer(exit_code=0)
    client = _FakeClient(container=container)
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    rt.run(["true"])
    call = client.containers.create_calls[0]
    volumes = call["volumes"]
    assert str(tmp_path.resolve()) in volumes
    assert volumes[str(tmp_path.resolve())]["bind"] == "/workdir"
    assert volumes[str(tmp_path.resolve())]["mode"] == "rw"
    assert call["working_dir"] == "/workdir"


def test_run_merges_env(tmp_path: Path) -> None:
    container = _FakeContainer(exit_code=0)
    client = _FakeClient(container=container)
    rt = DockerRuntime(
        image="alpine",
        workdir=tmp_path,
        env={"A": "1"},
        docker_client=client,
    )
    rt.run(["true"], env_overrides={"B": "2", "A": "override"})
    call = client.containers.create_calls[0]
    assert call["environment"] == {"A": "override", "B": "2"}


def test_run_extra_mounts(tmp_path: Path) -> None:
    extra_dir = tmp_path / "extra"
    extra_dir.mkdir()
    container = _FakeContainer(exit_code=0)
    client = _FakeClient(container=container)
    rt = DockerRuntime(
        image="alpine",
        workdir=tmp_path,
        docker_client=client,
        extra_mounts=[(extra_dir, "/extra", True)],
    )
    rt.run(["true"])
    call = client.containers.create_calls[0]
    volumes = call["volumes"]
    assert str(extra_dir.resolve()) in volumes
    assert volumes[str(extra_dir.resolve())]["bind"] == "/extra"
    assert volumes[str(extra_dir.resolve())]["mode"] == "ro"


def test_resources_override(tmp_path: Path) -> None:
    container = _FakeContainer(exit_code=0)
    client = _FakeClient(container=container)
    rt = DockerRuntime(
        image="alpine",
        workdir=tmp_path,
        docker_client=client,
        resources=DockerResources(
            mem_limit="512m",
            cpu_quota=50_000,
            pids_limit=128,
        ),
    )
    rt.run(["true"])
    call = client.containers.create_calls[0]
    assert call["mem_limit"] == "512m"
    assert call["cpu_quota"] == 50_000
    assert call["pids_limit"] == 128


def test_context_manager_pulls_image_on_enter(tmp_path: Path) -> None:
    client = _FakeClient(images=_FakeImages(has_image=False))
    with DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client):
        pass
    assert client.images.pulled == ["alpine"]


def test_container_removed_even_on_wait_error(tmp_path: Path) -> None:
    container = _FakeContainer(
        exit_code=0,
        timeout_exc=RuntimeError("wait broken"),
    )
    client = _FakeClient(container=container)
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    rt.run(["true"])
    assert container.removed is True


def test_remove_failure_does_not_raise(tmp_path: Path) -> None:
    """If container.remove() raises, the result still returns cleanly."""

    class _BadRemoveContainer(_FakeContainer):
        def remove(self, *, force: bool) -> None:
            raise RuntimeError("remove failed")

    container = _BadRemoveContainer(exit_code=0, stdout=b"ok")
    client = _FakeClient(container=container)
    rt = DockerRuntime(image="alpine", workdir=tmp_path, docker_client=client)
    result = rt.run(["true"])
    assert result.exit_code == 0
    assert result.stdout == "ok"
