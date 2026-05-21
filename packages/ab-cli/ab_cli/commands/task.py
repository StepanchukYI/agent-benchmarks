"""`ab task` — validate, list, and dry-run benchmark tasks."""

from __future__ import annotations

from pathlib import Path

import typer
from ab_datasets.loaders import load_task
from rich.table import Table

from ..ui import console

task_app = typer.Typer(
    name="task",
    help="Validate / list / dry-run tasks.",
    no_args_is_help=True,
    pretty_exceptions_enable=False,
)


def _datasets_root() -> Path:
    here = Path(__file__).resolve()
    # commands/task.py -> ab_cli -> ab-cli -> packages -> repo root
    repo_root = here.parents[4]
    return repo_root / "packages" / "ab-datasets" / "ab_datasets"


def _collect_yaml_paths(target: Path) -> list[Path]:
    if target.is_dir():
        return sorted(target.rglob("*.yaml"))
    if target.exists():
        return [target]
    parent = target.parent if target.parent != Path("") else Path(".")
    if parent.exists():
        matches = sorted(parent.glob(target.name))
        if matches:
            return matches
    return []


@task_app.command("validate", help="Validate one or more task YAML files.")
def validate(
    path: str = typer.Argument(..., help="File, directory, or glob to validate."),
) -> None:
    target = Path(path)
    paths = _collect_yaml_paths(target)
    if not paths:
        console.print(f"[red]error:[/red] no YAML files matched: {path}")
        raise typer.Exit(code=1)

    ok = 0
    failed = 0
    for p in paths:
        try:
            task = load_task(p)
        except Exception as exc:
            failed += 1
            console.print(f"[red]invalid:[/red] {p} — {exc}")
            continue
        ok += 1
        console.print(
            f"[green]valid:[/green] {task.id} (layer={task.layer.value}, suite={task.suite}) [{p}]"
        )

    console.print(f"\nsummary: {ok} valid, {failed} failed (total {len(paths)})")
    if failed:
        raise typer.Exit(code=1)


@task_app.command("dry-run", help="Load a task by id and verify its fixture path.")
def dry_run(
    task_id: str = typer.Argument(..., help="Task id, e.g. L0_001."),
) -> None:
    root = _datasets_root()
    matches: list[Path] = []
    for p in root.rglob("*.yaml"):
        try:
            task = load_task(p)
        except Exception:
            continue
        if task.id == task_id:
            matches.append(p)

    if not matches:
        console.print(f"[red]error:[/red] no task found with id {task_id} under {root}")
        raise typer.Exit(code=1)
    if len(matches) > 1:
        console.print(
            f"[red]error:[/red] multiple tasks share id {task_id}: " + ", ".join(str(m) for m in matches)
        )
        raise typer.Exit(code=1)

    yaml_path = matches[0]
    task = load_task(yaml_path)

    scorer_names = [s.name for s in task.scorer_chain]
    fixture_exists: bool | None
    fixture_path: Path | None = None
    if task.fixture_ref:
        repo_root = root.parent.parent.parent
        candidate = repo_root / task.fixture_ref
        if not candidate.exists():
            candidate = root.parent / task.fixture_ref
        fixture_path = candidate
        fixture_exists = candidate.exists()
    else:
        fixture_exists = None

    console.print(f"[bold]task[/bold]: {task.id}")
    console.print(f"  yaml:           {yaml_path}")
    console.print(f"  layer:          {task.layer.value}")
    console.print(f"  suite:          {task.suite}")
    console.print(f"  required_tier:  {task.config.required_tier}")
    console.print(f"  also_run_on:    {task.config.also_run_on}")
    console.print(f"  difficulty:     {task.difficulty.value}")
    console.print(f"  visibility:     {task.visibility.value}")
    console.print(f"  trust_ceiling:  {task.trust_tier_ceiling.value}")
    console.print(f"  scorers:        {scorer_names}")
    if task.fixture_ref:
        marker = "[green]ok[/green]" if fixture_exists else "[red]missing[/red]"
        console.print(f"  fixture_ref:    {task.fixture_ref} -> {fixture_path} ({marker})")
    else:
        console.print("  fixture_ref:    (none)")

    if task.fixture_ref and not fixture_exists:
        raise typer.Exit(code=1)


@task_app.command("list", help="List all known tasks as a table.")
def list_tasks() -> None:
    root = _datasets_root()
    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for p in sorted(root.rglob("*.yaml")):
        try:
            task = load_task(p)
        except Exception as exc:
            console.print(f"[red]skip:[/red] {p} — {exc}")
            continue
        rows.append(
            (
                task.id,
                task.layer.value,
                task.suite,
                task.config.required_tier,
                task.difficulty.value,
                str(len(task.scorer_chain)),
                str(p.relative_to(root)),
            )
        )

    table = Table(title="ab-datasets tasks", show_lines=False)
    table.add_column("id", style="cyan", no_wrap=True)
    table.add_column("layer")
    table.add_column("suite")
    table.add_column("tier")
    table.add_column("difficulty")
    table.add_column("scorers", justify="right")
    table.add_column("path")
    for row in sorted(rows):
        table.add_row(*row)
    console.print(table)
