from __future__ import annotations

import typer

from ergon.agents.base import AgentNotAvailable
from ergon.core.orchestrator import RunPipelineResult, RunTargetError, run_pipeline
from ergon.core.project import Project, ProjectNotInitialized
from ergon.ui.console import error, info, success, warn


def run(
    target: str = typer.Argument(..., help="Existing task id or new task description"),
    agent: str | None = typer.Option(
        None, "--agent", "-a", help="Implementer agent override"
    ),
    planner: str | None = typer.Option(
        None, "--planner", help="Planner agent override"
    ),
    reviewers: list[str] | None = typer.Option(
        None,
        "--reviewers",
        help="Reviewer agent override (repeat flag for multiple reviewers)",
    ),
    skip_plan: bool = typer.Option(False, "--skip-plan", help="Skip the planning step"),
    skip_validate: bool = typer.Option(
        False, "--skip-validate", help="Skip validation after implementation"
    ),
    skip_review: bool = typer.Option(
        False, "--skip-review", help="Skip review after validation"
    ),
    force: bool = typer.Option(
        False, "--force", help="Re-run completed phases instead of reusing status"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview what would run without changing files"
    ),
) -> None:
    """Create or resume a task and run its MVP pipeline."""
    try:
        project = Project.discover()
    except ProjectNotInitialized as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    try:
        result = run_pipeline(
            project=project,
            target=target,
            implementer=agent,
            planner=planner,
            reviewers=reviewers,
            skip_plan=skip_plan,
            skip_validate=skip_validate,
            skip_review=skip_review,
            force=force,
            dry_run=dry_run,
        )
    except (AgentNotAvailable, RunTargetError) as e:
        error(str(e))
        raise typer.Exit(code=2) from e
    except RuntimeError as e:
        error(str(e))
        raise typer.Exit(code=1) from e

    _print_run_result(result)

    if result.validation_failed:
        raise typer.Exit(code=1)
    if result.stopped_reason and not dry_run:
        raise typer.Exit(code=1)


def _print_run_result(result: RunPipelineResult) -> None:
    prefix = "Would use" if result.dry_run else "Using"
    if result.created:
        verb = "would create" if result.dry_run else "created"
        info(f"{prefix} task {result.task_id}: {result.task_title} ({verb} from description)")
    else:
        info(f"{prefix} task {result.task_id}: {result.task_title}")

    info(
        f"Agents: planner={result.planner_agent} "
        f"implementer={result.implementer_agent} "
        f"reviewers={', '.join(result.reviewer_agents) if result.reviewer_agents else '(none)'}"
    )

    for step in result.steps:
        line = f"{step.name}: {step.outcome}"
        if step.detail:
            line = f"{line} ({step.detail})"
        if step.outcome in {"ran", "would-run"}:
            success(line)
        elif step.outcome == "skipped":
            warn(line)
        else:
            info(line)

    if result.summary_path is not None:
        info(f"Summary: {result.summary_path.relative_to(result.project_root)}")

    if result.validation_failed:
        error("Run stopped after validation failure.")
    elif result.stopped_reason:
        warn(f"Run stopped: {result.stopped_reason}")
    elif result.dry_run:
        success("Dry run complete.")
    else:
        success("Run complete.")
