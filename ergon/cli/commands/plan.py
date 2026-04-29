from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import plan, resolve_role_or_raise
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id, e.g. 001"),
    agent: str | None = typer.Option(
        None, "--agent", "-a", help="Planner agent (overrides project / task default)"
    ),
) -> None:
    """Run the planner agent for a task."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        task, _ = load_task(project, task_id)
    except FileNotFoundError as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        resolution = resolve_role_or_raise(
            role_name="planner",
            explicit_agent=agent,
            task=task,
            project=project,
            builtin_fallback="openai",
        )
    except ValueError as e:
        error(str(e))
        raise typer.Exit(code=2) from e
    chosen = resolution.selected_agent

    try:
        task, artifacts, invocation = plan(project, task_id, chosen)
    except AgentNotAvailable as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if invocation.exit_code == 0:
        success(f"Plan from {chosen} written to plan.md")
    else:
        warn(f"Planner exited with code {invocation.exit_code}")
    info(f"Resolved from: {resolution.source}")
    info(f"Plan: {artifacts.plan_md.relative_to(project.root)}")
