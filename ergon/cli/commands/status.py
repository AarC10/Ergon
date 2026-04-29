from __future__ import annotations

import typer
from rich.panel import Panel
from rich.table import Table

from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import console, error


_ARTIFACTS = (
    ("brief.md", "brief.md"),
    ("plan.md", "plan.md"),
    ("implementation-log.md", "implementation-log.md"),
    ("diff.patch", "diff.patch"),
    ("changed_files.txt", "changed_files.txt"),
    ("validation.log", "validation.log"),
    ("review-summary.md", "review-summary.md"),
    ("run-summary.md", "run-summary.md"),
    ("final.md", "final.md"),
)


def run(task_id: str | None = typer.Argument(None, help="Optional task id")) -> None:
    """Show project / task status."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if task_id is None:
        _print_project_status(project)
        return

    try:
        task, artifacts = load_task(project, task_id)
    except FileNotFoundError as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    body = (
        f"[bold]Task {task.id}[/bold]: {task.title}\n"
        f"Status: [magenta]{task.status}[/magenta]    Type: {task.type}\n"
        f"Repo: {task.repo}    Base branch: {task.base_branch}\n"
        f"Worktree: {task.worktree_path or '-'}\n"
        f"Branch:   {task.branch_name or '-'}\n"
        f"Safety:   {task.safety_level}    Manual gate: {task.manual_gate}"
    )
    console.print(Panel(body, title=f"task {task.id}", border_style="cyan"))

    table = Table(title="Artifacts", show_header=True)
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Size", justify="right")
    table.add_column("State")
    listed: set[str] = set()
    for name, fname in _ARTIFACTS:
        path = artifacts.root / fname
        listed.add(fname)
        if path.exists():
            table.add_row(name, str(path.stat().st_size), "[green]ok[/green]")
        else:
            table.add_row(name, "-", "[dim]missing[/dim]")
    # Per-agent files (logs, per-agent reports). Avoid double-listing the
    # canonical artifacts above.
    extras = sorted(
        p for p in artifacts.root.iterdir()
        if p.is_file() and p.name not in listed
    )
    for p in extras:
        table.add_row(p.name, str(p.stat().st_size), "[green]ok[/green]")
    console.print(table)


def _print_project_status(project: Project) -> None:
    body = (
        f"[bold]{project.config.name}[/bold] ({project.config.type})\n"
        f"Root: {project.root}\n"
        f"Default branch: {project.config.default_branch}\n"
        f"Safety level:   {project.config.rules.safety_level}\n"
        f"Auto-merge / push: {project.config.rules.auto_merge} / "
        f"{project.config.rules.auto_push}"
    )
    console.print(Panel(body, title="project", border_style="cyan"))

    folders = sorted(p for p in project.tasks_dir.iterdir() if p.is_dir())
    if not folders:
        console.print("[dim]No tasks yet.[/dim]")
        return
    by_status: dict[str, int] = {}
    for folder in folders:
        try:
            task_yaml = folder / "task.yaml"
            if not task_yaml.exists():
                continue
            from ergon.core.artifact_store import TaskArtifacts

            t = TaskArtifacts(root=folder).load_task()
            by_status[t.status] = by_status.get(t.status, 0) + 1
        except Exception:
            continue
    summary = "  ".join(f"{k}: {v}" for k, v in sorted(by_status.items()))
    console.print(f"[bold]{len(folders)} tasks[/bold]    {summary}")
