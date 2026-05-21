"""`ab wizard` — interactive picker for runner / model / effort / suite / tier.

Operator runs `ab wizard` and walks numbered prompts. The wizard prints the
equivalent `ab run` invocation at the end, optionally executes it. Zero new
deps; uses Typer's built-in `prompt` + manual numbered lists.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import typer
from ab_harness.models import (
    MODEL_REGISTRY,
    PRIORITY_SCAFFOLDS_V1,
    VENDOR_BASE_URLS,
    models_for_runner,
)

from ..ui import console

_RUNNERS_FRIENDLY: dict[str, str] = {
    "claude-code": "Anthropic Claude Code (claude CLI)",
    "codex-cli":   "OpenAI Codex CLI (codex)",
    "gemini-cli":  "Google Gemini CLI (gemini)",
    "opencode":    "OpenCode CLI (opencode.ai)",
    "pi-agent":    "Pi coding agent (pi.dev)",
    "anthropic-compat": "Anthropic-compat HTTP (Zhipu / MiniMax / Moonshot / DeepSeek)",
    "openai-compat":    "OpenAI-compat HTTP (OpenAI / vLLM / TGI / etc.)",
    "local":       "Local OpenAI-compat (Ollama / LM Studio / llama.cpp)",
    "mock":        "Mock runner (no live calls — smoke test only)",
}

_EFFORT_LEVELS: tuple[str, ...] = ("low", "medium", "high", "xhigh", "max")

_SUITES: tuple[tuple[str, str], ...] = (
    ("L0_smoke", "L0 foundation smoke (39 tasks)"),
    ("L1_memory", "L1 memory write-in-flight"),
    ("L2_skills", "L2 skill/MCP routing"),
    ("L3_domains", "L3 per-domain adapters"),
    ("L4_composite", "L4 composite real-world"),
)

_TIERS: tuple[tuple[str, str], ...] = (
    ("T0", "Vanilla — no CLAUDE.md, no skills, no MCPs"),
    ("T1", "Minimal — generic CLAUDE.md, no skills"),
    ("T2", "Personal — vault + CLAUDE.md + skills"),
    ("T3", "Full — vault + CLAUDE.md + skills + MCPs"),
)


def _pick(label: str, choices: list[tuple[str, str]], *, default_idx: int = 0) -> str:
    """Numbered picker. Returns the chosen value (first column)."""
    console.print(f"\n[bold]{label}[/bold]")
    for i, (val, desc) in enumerate(choices, start=1):
        marker = "[dim]·[/dim]" if i - 1 != default_idx else "[green]→[/green]"
        console.print(f"  {marker} {i:>2}. [cyan]{val:<22}[/cyan] {desc}")
    raw = typer.prompt(
        f"pick 1-{len(choices)}",
        default=str(default_idx + 1),
        show_default=True,
    )
    try:
        idx = int(raw) - 1
    except ValueError:
        idx = default_idx
    if not 0 <= idx < len(choices):
        idx = default_idx
    return choices[idx][0]


def _pick_model(runner: str) -> str:
    candidates = models_for_runner(runner)
    if not candidates:
        candidates = list(MODEL_REGISTRY)
    pairs: list[tuple[str, str]] = []
    for m in candidates[:30]:
        tag = "local" if m.local else m.family
        # Pricing is per-1M tokens in the registry; show per-1k for parity
        # with how operators talk about cost.
        cost_in = m.input_usd_per_1m / 1000.0
        cost_out = m.output_usd_per_1m / 1000.0
        pairs.append(
            (
                m.id,
                f"{m.id:<26} {tag:<10} ${cost_in:.4g}/${cost_out:.4g} per 1k",
            )
        )
    if len(candidates) > 30:
        console.print(
            f"[dim]({len(candidates) - 30} more — pass via --model if not listed)[/dim]"
        )
    return _pick("Model", pairs)


def _pick_vendor() -> str | None:
    """For anthropic-compat / claude-code: pick a vendor route."""
    pairs = [("anthropic", "Anthropic (default)")]
    for v in VENDOR_BASE_URLS:
        if v == "anthropic":
            continue
        pairs.append((v, f"Route via {v}"))
    pairs.append(("(skip)", "No vendor route"))
    pick = _pick("Vendor (claude-code only)", pairs)
    return None if pick == "(skip)" else pick


def wizard(
    execute: bool = typer.Option(
        True,
        "--execute/--dry",
        help="Run the `ab run` invocation at the end. --dry just prints it.",
    ),
    results_root: Path = typer.Option(
        Path.home() / ".ab" / "results",
        help="Where the wizard tells `ab run` to write its run dir.",
    ),
) -> None:
    """Interactive picker. Walks runner → model → effort → suite → tier."""
    console.print("[bold]ab wizard[/bold] — pick runner, model, effort, suite, tier.")
    console.print("[dim]Hit Enter to accept defaults.[/dim]")

    runner_pairs = [
        (r, _RUNNERS_FRIENDLY.get(r, r))
        for r in [*PRIORITY_SCAFFOLDS_V1, "anthropic-compat", "openai-compat", "local", "mock"]
    ]
    runner = _pick("Runner", runner_pairs)

    model = _pick_model(runner)

    if runner in {"claude-code", "codex-cli", "gemini-cli", "opencode", "pi-agent"}:
        effort_pairs = [(e, f"reasoning effort = {e}") for e in _EFFORT_LEVELS]
        effort: str | None = _pick("Effort", effort_pairs, default_idx=1)
    else:
        effort = None

    vendor: str | None = None
    if runner == "claude-code":
        vendor = _pick_vendor()

    suite = _pick("Suite", list(_SUITES))
    tier = _pick("Tier", list(_TIERS))

    task = typer.prompt(
        "Single task id (blank = run whole suite)",
        default="",
        show_default=False,
    ).strip()

    # Assemble the invocation.
    argv: list[str] = [
        "ab", "run",
        "--suite", suite,
        "--runner", runner,
        "--model", model,
        "--tier", tier,
        "--results-root", str(results_root),
    ]
    if task:
        argv += ["--task", task]
    if effort:
        argv += ["--effort", effort]
    if vendor:
        argv += ["--vendor", vendor]

    console.print("\n[bold]Invocation[/bold]")
    console.print("  [green]" + " ".join(argv) + "[/green]\n")

    if not execute:
        return

    confirm = typer.prompt("execute? [y/N]", default="y", show_default=True)
    if confirm.strip().lower() not in {"y", "yes"}:
        console.print("[yellow]skipped[/yellow]")
        return

    # Inherit env so vendor tokens (ANTHROPIC_AUTH_TOKEN etc) reach the
    # subprocess. Invoke the same `ab` console script that's on PATH inside
    # this venv (uv installs it next to the python entrypoint).
    ab_bin = Path(sys.executable).with_name("ab")
    cmd = [str(ab_bin) if ab_bin.exists() else "ab", *argv[1:]]
    ret = subprocess.call(cmd)
    if ret != 0:
        raise typer.Exit(ret)
