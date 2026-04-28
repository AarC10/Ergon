from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import implement
from ergon.core.project import Project, ProjectNotInitialized
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id, e.g. 001"),
    agent: str = typer.Option("claude", "--agent", "-a", help="Agent name"),
    extra: str | None = typer.Option(None, "--extra", help="Extra prompt text"),
) -> None:
    """Invoke the implementer agent for a task in its worktree."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        task, artifacts, invocation = implement(project, task_id, agent, extra)
    except AgentNotAvailable as e:
        error(str(e))
        raise typer.Exit(code=2) from e
    except FileNotFoundError as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if invocation.exit_code == 0:
        success(f"Implementer {agent} finished cleanly for task {task.id}")
    else:
        warn(f"Implementer exited with code {invocation.exit_code}")
    info(f"Worktree: {task.worktree_path}")
    info(f"Branch:   {task.branch_name}")
    info(f"Diff:     {artifacts.diff_patch.relative_to(project.root)}")
    info(f"Log:      {invocation.log_path.relative_to(project.root)}")
