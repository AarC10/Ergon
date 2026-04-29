from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import SafetyViolation, implement, resolve_agent_choice
from ergon.core.project import Project, ProjectNotInitialized
from ergon.core.task import load_task
from ergon.ui.console import error, info, success, warn


def run(
    task_id: str = typer.Argument(..., help="Task id"),
    agent: str | None = typer.Option(
        None, "--agent", "-a", help="Implementer agent (overrides project / task default)"
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

    chosen = resolve_agent_choice(
        explicit=agent,
        task=task,
        project=project,
        role="implementer",
        fallback="claude",
    )

    try:
        task, artifacts, invocation = implement(project, task_id, chosen, extra)
    except AgentNotAvailable as e:
        error(str(e))
        raise typer.Exit(code=2) from e
    except SafetyViolation as e:
        error(str(e))
        raise typer.Exit(code=2) from e

    if invocation.exit_code == 0:
        success(f"Implementer {chosen} finished cleanly for task {task.id}")
    else:
        warn(f"Implementer exited with code {invocation.exit_code}")
    info(f"Worktree: {task.worktree_path}")
    info(f"Branch:   {task.branch_name}")
    info(f"Diff:     {artifacts.diff_patch.relative_to(project.root)}")
    info(f"Log:      {invocation.log_path.relative_to(project.root)}")
