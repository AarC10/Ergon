from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import debug
from ergon.core.project import Project, ProjectNotInitialized
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agent: str = typer.Option("openai", "--agent", "-a"),
    extra_logs: str = typer.Option("", "--logs", help="Extra free-form log text"),
) -> None:
    """Run the debugger agent for a task."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        task, artifacts, invocation = debug(project, task_id, agent, extra_logs)
    except (AgentNotAvailable, FileNotFoundError) as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if invocation.exit_code == 0:
        success(f"Debug report from {agent} complete")
    else:
        warn(f"Debugger exited with code {invocation.exit_code}")
    info(f"Report: {(artifacts.root / f'debug-{agent}.md').relative_to(project.root)}")
