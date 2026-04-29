from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import debug, resolve_role_or_raise
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agent: str | None = typer.Option(
        None, "--agent", "-a", help="Debugger agent (overrides project / task default)"
    ),
    extra_logs: str = typer.Option("", "--logs", help="Extra free-form log text"),
) -> None:
    """Run the debugger agent for a task."""
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
            role_name="debugger",
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
        task, artifacts, invocation = debug(project, task_id, chosen, extra_logs)
    except AgentNotAvailable as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    if invocation.exit_code == 0:
        success(f"Debug report from {chosen} complete")
    else:
        warn(f"Debugger exited with code {invocation.exit_code}")
    info(f"Resolved from: {resolution.source}")
    info(f"Report: {(artifacts.root / f'debug-{chosen}.md').relative_to(project.root)}")
