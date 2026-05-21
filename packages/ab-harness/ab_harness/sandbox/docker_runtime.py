"""Future container-backed materialization (build spec sec 7).

Phase 2 work. v1 runs claude on the host via `docker.materialize()`; this
module pulls the base image, mounts CLAUDE.md and `.claude/`, installs skills
into `/sessions/.../mnt/.claude/skills/`, untars the vault snapshot into
`/vault/`, and starts the runner inside the container.
"""

from __future__ import annotations


class DockerRuntime:
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "DockerRuntime is a Phase 2 placeholder; see build spec sec 7."
        )
