"""Tier materializer (build spec sec 7).

v1 runs claude on the host inside a fresh workdir with tier files copied in.
The module keeps the name `docker` for back-compat; real container work lives
in `docker_runtime.py`.
"""

from __future__ import annotations

import shutil
import tarfile
from pathlib import Path
from typing import Any

from ab_datasets.schemas import Tier
from pydantic import BaseModel, ConfigDict

from .manifest import compute_total_sha256, load_manifest

_TIER_SLUG = {
    Tier.T0: "vanilla",
    Tier.T1: "minimal",
    Tier.T2: "personal",
    Tier.T3: "full",
}


def slug_for_tier(tier: Tier) -> str:
    return _TIER_SLUG[tier]


class MaterializedTier(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    tier: Tier
    tier_hash: str
    workdir: Path
    manifest_path: Path


def _resolve(root: Path, ref: str) -> Path:
    p = Path(ref)
    if p.is_absolute():
        return p
    candidate = root / ref
    if candidate.exists():
        return candidate
    return root.parent.parent / ref


def materialize(
    tier_fixtures_root: Path,
    tier: Tier,
    task: Any,
    workdir: Path,
) -> MaterializedTier:
    tier_fixtures_root = Path(tier_fixtures_root)
    workdir = Path(workdir)
    manifest_dir = tier_fixtures_root / f"{tier.value}_{slug_for_tier(tier)}"
    manifest_path = manifest_dir / "manifest.yaml"
    manifest = load_manifest(manifest_path)

    workdir.mkdir(parents=True, exist_ok=True)
    claude_dir = workdir / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)

    if manifest.claude_md:
        src = _resolve(manifest_dir, manifest.claude_md["path"])
        shutil.copyfile(src, workdir / "CLAUDE.md")

    if manifest.claude_local_md:
        src = _resolve(manifest_dir, manifest.claude_local_md["path"])
        shutil.copyfile(src, claude_dir / "CLAUDE.local.md")

    skill_ids = [s["id"] for s in manifest.skills]
    (claude_dir / "SKILLS.txt").write_text(
        "\n".join(skill_ids) + ("\n" if skill_ids else ""), encoding="utf-8"
    )

    mcp_ids = [m["id"] for m in manifest.mcps]
    (claude_dir / "MCPS.txt").write_text(
        "\n".join(mcp_ids) + ("\n" if mcp_ids else ""), encoding="utf-8"
    )

    if manifest.vault_state and manifest.vault_state.get("snapshot"):
        snap = _resolve(manifest_dir, manifest.vault_state["snapshot"])
        vault_dir = workdir / "vault"
        vault_dir.mkdir(parents=True, exist_ok=True)
        with tarfile.open(snap, "r:*") as tar:
            for member in tar.getmembers():
                # Reject absolute paths and parent-escapes; safe extract.
                if member.name.startswith("/") or ".." in Path(member.name).parts:
                    raise ValueError(f"unsafe tar entry: {member.name}")
            tar.extractall(vault_dir)

    tier_hash = compute_total_sha256(manifest, manifest_dir)

    return MaterializedTier(
        tier=tier,
        tier_hash=tier_hash,
        workdir=workdir,
        manifest_path=manifest_path,
    )
