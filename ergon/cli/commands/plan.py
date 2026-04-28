from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import plan
from ergon.core.project import Project, ProjectNotInitialized
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id, e.g. 001"),
    agent: str = typer.Option("openai", "--agent", "-a", help="Planner agent"),
) -> None:
    """Run the planner agent for a task."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        task, artifacts, invocation = plan(project, task_id, agent)
    except (AgentNotAvailable, FileNotFoundError) as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if invocation.exit_code == 0:
        success(f"Plan from {agent} written to plan.md")
    else:
        warn(f"Planner exited with code {invocation.exit_code}")
    info(f"Plan: {artifacts.plan_md.relative_to(project.root)}")
