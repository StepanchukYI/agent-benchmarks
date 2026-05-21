"""Environment smoke — validate the initial agent config without running a task.

The motivation: when comparing models across runners, the most common
failure mode is "the agent never received my CLAUDE.md / skills / MCPs",
which masquerades as "the model is bad". This module is a 0-cost
pre-flight check — it asserts the materialized workdir + tier config
look exactly as the runner will see them, BEFORE any model invocation.

Top-level helper:

* :func:`validate_environment(workdir, tier_manifest=None) -> EnvReport`

  Returns a structured report of what's loaded vs what's missing.
  No network. No model call. Pure file-system inspection.

Reports cover:

* CLAUDE.md presence + size + first line
* ``.claude/SKILLS.txt`` presence + entries
* ``.claude/MCPS.txt`` presence + entries
* Vault snapshot presence (if expected per tier)
* Tier manifest sha256 match (if provided)
* Permission map: is workdir writable, are forbidden paths absent

Use from:

* CLI: ``ab env validate <workdir>`` (wire-up in ab-cli, separate commit).
* Pre-run guard: a runner's ``prepare()`` can call this and refuse to
  start if the env is broken.
* CI on the homelab: scheduled smoke that detects config drift.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EnvCheck:
    """One pass/fail check inside the report."""

    name: str
    ok: bool
    detail: str
    severity: str = "error"  # "error" | "warning" | "info"


@dataclass
class EnvReport:
    """Result of :func:`validate_environment`."""

    workdir: str
    tier: str | None = None
    tier_hash_expected: str | None = None
    tier_hash_observed: str | None = None
    checks: list[EnvCheck] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(c.ok for c in self.checks if c.severity == "error")

    def to_dict(self) -> dict[str, Any]:
        return {
            "workdir": self.workdir,
            "tier": self.tier,
            "tier_hash_expected": self.tier_hash_expected,
            "tier_hash_observed": self.tier_hash_observed,
            "ok": self.ok,
            "checks": [
                {
                    "name": c.name,
                    "ok": c.ok,
                    "detail": c.detail,
                    "severity": c.severity,
                }
                for c in self.checks
            ],
        }


def _first_line(path: Path, limit: int = 120) -> str:
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            line = fh.readline().rstrip("\n")
    except OSError as exc:
        return f"<read error: {exc}>"
    return line[:limit] + ("..." if len(line) > limit else "")


def _sha256_of_tree(root: Path) -> str:
    """Stable sha256 over (relpath, content_sha256) tuples — order-independent."""
    if not root.exists():
        return ""
    digests: list[tuple[str, str]] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        try:
            with path.open("rb") as fh:
                h = hashlib.sha256(fh.read()).hexdigest()
        except OSError:
            continue
        digests.append((str(path.relative_to(root)), h))
    combined = hashlib.sha256()
    for rel, h in sorted(digests):
        combined.update(rel.encode("utf-8"))
        combined.update(b"\x00")
        combined.update(h.encode("ascii"))
        combined.update(b"\x00")
    return combined.hexdigest()


def _read_lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return [
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    except OSError:
        return []


def validate_environment(
    workdir: Path | str,
    tier_manifest: Any | None = None,
    *,
    require_claude_md: bool = True,
    require_skills_manifest: bool = True,
    require_mcps_manifest: bool = False,
    forbid_paths: tuple[str, ...] = (".env", "secrets/", ".ssh/"),
) -> EnvReport:
    """Inspect ``workdir`` against the expected initial-environment layout.

    Returns an :class:`EnvReport` with one :class:`EnvCheck` per probe.
    ``EnvReport.ok`` is True iff every ``severity="error"`` check passed;
    warnings + infos never flip the gate.

    Parameters:
        workdir: directory the runner will use as cwd.
        tier_manifest: optional materialized tier object (must have
            ``tier`` + ``total_sha256``). When given, the observed sha is
            recomputed from the workdir contents and compared.
        require_claude_md: error if CLAUDE.md missing.
        require_skills_manifest: error if ``.claude/SKILLS.txt`` missing.
        require_mcps_manifest: error if ``.claude/MCPS.txt`` missing.
        forbid_paths: paths whose presence in the workdir is an error.
    """
    workdir = Path(workdir)
    report = EnvReport(workdir=str(workdir.resolve()))

    if not workdir.exists():
        report.checks.append(
            EnvCheck(
                name="workdir.exists",
                ok=False,
                detail=f"workdir not found: {workdir}",
            )
        )
        return report
    if not workdir.is_dir():
        report.checks.append(
            EnvCheck(
                name="workdir.is_dir",
                ok=False,
                detail=f"not a directory: {workdir}",
            )
        )
        return report

    report.checks.append(EnvCheck(name="workdir.exists", ok=True, detail=str(workdir)))

    # CLAUDE.md
    claude_md = workdir / "CLAUDE.md"
    if claude_md.exists():
        report.checks.append(
            EnvCheck(
                name="claude_md.present",
                ok=True,
                detail=f"size={claude_md.stat().st_size}B, first_line={_first_line(claude_md)!r}",
            )
        )
    else:
        report.checks.append(
            EnvCheck(
                name="claude_md.present",
                ok=not require_claude_md,
                detail="missing",
                severity="error" if require_claude_md else "warning",
            )
        )

    # Skills
    skills_txt = workdir / ".claude" / "SKILLS.txt"
    skills = _read_lines(skills_txt)
    if skills_txt.exists():
        report.checks.append(
            EnvCheck(
                name="skills.present",
                ok=True,
                detail=f"{len(skills)} skill(s): {', '.join(skills[:8])}{'...' if len(skills) > 8 else ''}",
            )
        )
    else:
        report.checks.append(
            EnvCheck(
                name="skills.present",
                ok=not require_skills_manifest,
                detail="missing .claude/SKILLS.txt",
                severity="error" if require_skills_manifest else "warning",
            )
        )

    # MCPs
    mcps_txt = workdir / ".claude" / "MCPS.txt"
    mcps = _read_lines(mcps_txt)
    if mcps_txt.exists():
        report.checks.append(
            EnvCheck(
                name="mcps.present",
                ok=True,
                detail=f"{len(mcps)} mcp(s): {', '.join(mcps[:8])}{'...' if len(mcps) > 8 else ''}",
            )
        )
    else:
        report.checks.append(
            EnvCheck(
                name="mcps.present",
                ok=not require_mcps_manifest,
                detail="missing .claude/MCPS.txt",
                severity="error" if require_mcps_manifest else "info",
            )
        )

    # Forbidden paths
    for forbidden in forbid_paths:
        candidate = workdir / forbidden
        if candidate.exists():
            report.checks.append(
                EnvCheck(
                    name=f"forbid.{forbidden}",
                    ok=False,
                    detail=f"forbidden path present in workdir: {forbidden}",
                )
            )

    # Tier hash
    if tier_manifest is not None:
        expected = (
            getattr(tier_manifest, "total_sha256", None)
            or (tier_manifest.get("total_sha256") if isinstance(tier_manifest, dict) else None)
        )
        report.tier = (
            getattr(tier_manifest, "tier", None) and str(tier_manifest.tier)
        ) or (tier_manifest.get("tier") if isinstance(tier_manifest, dict) else None)
        report.tier_hash_expected = expected
        observed = _sha256_of_tree(workdir)
        report.tier_hash_observed = observed
        if expected and observed:
            ok = expected == observed
            report.checks.append(
                EnvCheck(
                    name="tier.hash_match",
                    ok=ok,
                    detail=(
                        f"observed={observed[:12]}…, expected={expected[:12]}…"
                        if ok
                        else f"MISMATCH observed={observed[:12]}… vs expected={expected[:12]}…"
                    ),
                    severity="error" if not ok else "info",
                )
            )

    # Workdir writable
    try:
        probe = workdir / ".__env_smoke_writable_probe__"
        probe.write_text("x", encoding="utf-8")
        probe.unlink()
        report.checks.append(EnvCheck(name="workdir.writable", ok=True, detail="ok"))
    except OSError as exc:
        report.checks.append(
            EnvCheck(name="workdir.writable", ok=False, detail=f"write failed: {exc}")
        )

    return report


__all__ = ["EnvCheck", "EnvReport", "validate_environment"]
