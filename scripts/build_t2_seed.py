"""Build the deterministic T2 vault seed tarball.

Re-runnable: produces byte-identical output across machines because tar
entries are sorted and mtime is pinned to the 2026-05-21 epoch. Commit
both this script and the resulting `T2_seed_small.tar.gz`.
"""

from __future__ import annotations

import gzip
import io
import tarfile
from datetime import UTC, datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
OUTPUT = (
    REPO_ROOT
    / "packages"
    / "ab-datasets"
    / "fixtures"
    / "vault_snapshots"
    / "T2_seed_small.tar.gz"
)

PINNED_MTIME = int(datetime(2026, 5, 21, tzinfo=UTC).timestamp())

HUB_MD = """\
# Hub

Project: <example-project>
Owner: <operator>
Status: active
Updated: 2026-05-21
Notes: anonymized seed for T2 fixture; do not reference real systems.
"""

DECISIONS_MD = """\
# Decisions

<!-- append new entries above this line -->
"""

LESSONS_MD = """\
# Lessons

<!-- append new entries above this line -->
"""

FILES = [
    ("T2_seed_small/hub.md", HUB_MD),
    ("T2_seed_small/decisions.md", DECISIONS_MD),
    ("T2_seed_small/lessons.md", LESSONS_MD),
]


def _build_tar_bytes() -> bytes:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w", format=tarfile.USTAR_FORMAT) as tar:
        for name, content in sorted(FILES, key=lambda x: x[0]):
            data = content.encode("utf-8")
            info = tarfile.TarInfo(name=name)
            info.size = len(data)
            info.mtime = PINNED_MTIME
            info.mode = 0o644
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.type = tarfile.REGTYPE
            tar.addfile(info, io.BytesIO(data))
    return buf.getvalue()


def build() -> Path:
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    tar_bytes = _build_tar_bytes()
    with open(OUTPUT, "wb") as fh, gzip.GzipFile(
        filename="",
        mode="wb",
        fileobj=fh,
        mtime=PINNED_MTIME,
        compresslevel=9,
    ) as gz:
        gz.write(tar_bytes)
    return OUTPUT


if __name__ == "__main__":
    path = build()
    print(f"wrote {path} ({path.stat().st_size} bytes)")
