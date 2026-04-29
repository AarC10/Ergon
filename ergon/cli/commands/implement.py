from __future__ import annotations

import typer

from ergon.agents.base import AgentExecutionError, AgentNotAvailable
from ergon.core.orchestrator import (
    SafetyViolation,
    implement,
    resolve_role_or_raise,
)
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agent: str | None = typer.Option(
        None, "--agent", "-a", help="Implementer agent (overrides project / task default)"
    ),
    escalate: bool = typer.Option(
        False,
        "--escalate",
        help="Use the implementer escalation agent where configured",
    ),
    extra: str | None = typer.Option(None, "--extra", help="Extra prompt text"),
) -> None:
    """Invoke the implementer agent for a task in its worktree."""
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
            role_name="implementer",
            explicit_agent=agent,
            task=task,
            project=project,
            allow_escalation=escalate,
            builtin_fallback="claude",
        )
    except ValueError as e:
        error(str(e))
        raise typer.Exit(code=2) from e
    chosen = resolution.selected_agent

    try:
        task, artifacts, invocation = implement(project, task_id, chosen, extra)
    except AgentNotAvailable as e:
        error(str(e))
        raise typer.Exit(code=2) from e
    except AgentExecutionError as e:
        error(str(e))
        raise typer.Exit(code=1) from e
    except SafetyViolation as e:
        error(str(e))
        raise typer.Exit(code=2) from e

    if invocation.exit_code == 0:
        success(f"Implementer {chosen} finished cleanly for task {task.id}")
    else:
        warn(f"Implementer exited with code {invocation.exit_code}")
    info(f"Resolved from: {resolution.source}")
    info(f"Worktree: {task.worktree_path}")
    info(f"Branch:   {task.branch_name}")
    info(f"Diff:     {artifacts.diff_patch.relative_to(project.root)}")
    info(f"Log:      {invocation.log_path.relative_to(project.root)}")
