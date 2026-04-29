from __future__ import annotations

import typer
from pydantic import ValidationError
from rich.table import Table

from ergon.core.config import ROLE_NAMES
from ergon.core.orchestrator import resolve_role_or_raise
from ergon.core.project import Project, ProjectNotInitialized
from ergon.ui.console import console, error, info


def run(
    resolve: str | None = typer.Option(
        None,
        "--resolve",
        help="Resolve a single role and show the chosen agent",
    ),
    escalate: bool = typer.Option(
        False,
        "--escalate",
        help="Use escalation mappings where configured",
    ),
) -> None:
    """List effective role mappings."""
    project = _discover_optional_project()
    if project is not None:
        info(f"Project: {project.root}")

    try:
        if resolve:
            resolution = resolve_role_or_raise(
                role_name=resolve,
                project=project,
                allow_escalation=escalate,
            )
            table = Table(title=f"Role: {resolve}", show_header=True)
            table.add_column("Field", style="cyan", no_wrap=True)
            table.add_column("Value")
            table.add_row("Selected agent", resolution.selected_agent)
            table.add_row("Source", resolution.source)
            table.add_row(
                "Fallback candidates",
                ", ".join(resolution.fallback_candidates) or "(none)",
            )
            table.add_row(
                "Candidate chain",
                ", ".join(resolution.candidate_chain) or "(none)",
            )
            console.print(table)
            return
    except (ValueError, ValidationError, FileNotFoundError) as e:
        error(str(e))
        raise typer.Exit(code=2) from e

    table = Table(title="Roles", show_header=True)
    table.add_column("Role", style="cyan", no_wrap=True)
    table.add_column("Selected agent")
    table.add_column("Source")
    table.add_column("Fallbacks")
    for role_name in ROLE_NAMES:
        try:
            resolution = resolve_role_or_raise(
                role_name=role_name,
                project=project,
                allow_escalation=escalate,
            )
            fallbacks = ", ".join(resolution.fallback_candidates) or "-"
            table.add_row(
                role_name,
                resolution.selected_agent,
                resolution.source,
                fallbacks,
            )
        except ValueError as e:
            table.add_row(role_name, "[red]unresolved[/red]", str(e), "-")
    console.print(table)


def _discover_optional_project() -> Project | None:
    try:
        return Project.discover()
    except (ProjectNotInitialized, FileNotFoundError, ValidationError):
        return None
