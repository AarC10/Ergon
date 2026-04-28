from __future__ import annotations

from datetime import datetime
from pathlib import Path

from ergon.agents.base import AgentInvocation
from ergon.agents.registry import AgentRegistry
from ergon.core.artifact_store import TaskArtifacts
from ergon.core.config import TaskConfig
from ergon.core.project import Project
from ergon.core.task import load_task, update_status
from ergon.roles import prompts as role_prompts
from ergon.tools.commands import CommandResult, run_shell
from ergon.tools.git import changed_files as git_changed_files
from ergon.tools.git import diff_against
from ergon.tools.worktree import Worktree, create_worktree


# Files Ergon writes into the worktree to brief the agent. They are excluded
# from the task diff so the captured patch reflects only the agent's work.
_SCAFFOLD_FILES = (
    "ERGON_TASK.md",
    "ERGON_CONTEXT.md",
    "ERGON_CONSTRAINTS.md",
    "ERGON_PROMPT.md",
)


# ---- worktree-bound task setup ---------------------------------------------


def ensure_worktree(
    project: Project,
    task: TaskConfig,
    artifacts: TaskArtifacts,
    agent: str,
) -> Worktree:
    """Create or reuse the worktree for (task, agent), and update task.yaml."""
    repo_root = Path(project.config.repo_path)
    wt = create_worktree(
        repo_root=repo_root,
        repo_name=project.config.name,
        task_id=task.id,
        slug=task.slug,
        agent=agent,
        base_branch=task.base_branch,
    )
    task.worktree_path = str(wt.path)
    task.branch_name = wt.branch
    artifacts.save_task(task)
    _write_worktree_context(wt, project, task, artifacts)
    return wt


def _bullets(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- `{p}`" for p in items) if items else f"- {empty}"


def _bullets_plain(items: list[str], empty: str = "(none)") -> str:
    return "\n".join(f"- {p}" for p in items) if items else f"- {empty}"


def _write_worktree_context(
    wt: Worktree, project: Project, task: TaskConfig, artifacts: TaskArtifacts
) -> None:
    """Drop ERGON_TASK.md, ERGON_CONTEXT.md, ERGON_CONSTRAINTS.md into the worktree."""
    brief_rel = artifacts.brief_md.relative_to(project.root)
    (wt.path / "ERGON_TASK.md").write_text(
        f"""# Ergon Task {task.id}: {task.title}

Repo: {project.config.name}
Base branch: {task.base_branch}
Branch: {wt.branch}
Type: {task.type}
Safety: {task.safety_level}

## Goal

{task.goal}

## Brief

See `{brief_rel}` in the main repo.
""",
        encoding="utf-8",
    )

    includes = _bullets(task.scope.allowed_paths)
    excludes = _bullets(task.scope.forbidden_paths)
    (wt.path / "ERGON_CONTEXT.md").write_text(
        f"""# Ergon Context

## Allowed scope

{includes}

## Forbidden scope

{excludes}

## Project conventions

See `.ergon/memory/` in the main repo for architecture, decisions,
conventions, and glossary.
""",
        encoding="utf-8",
    )

    constraints = _bullets_plain(task.constraints, empty="(none specified)")
    validation = _bullets(task.validation.commands)
    (wt.path / "ERGON_CONSTRAINTS.md").write_text(
        f"""# Ergon Constraints

Manual approval required: {task.manual_gate}
Auto-merge: {project.config.rules.auto_merge}
Auto-push: {project.config.rules.auto_push}

## Constraints

{constraints}

## Validation

Run these commands before declaring done:

{validation}
""",
        encoding="utf-8",
    )


# ---- run helpers ------------------------------------------------------------


def make_invocation(
    agent_name: str,
    role: str,
    cwd: Path,
    prompt: str,
    log_path: Path,
) -> AgentInvocation:
    return AgentInvocation(
        agent_name=agent_name,
        role=role,
        cwd=cwd,
        prompt=prompt,
        log_path=log_path,
        started_at=datetime.now(),
    )


def capture_diff(project: Project, task: TaskConfig, artifacts: TaskArtifacts) -> None:
    """Save diff.patch and changed_files.txt by reading the worktree."""
    if not task.worktree_path:
        return
    wt_path = Path(task.worktree_path)
    if not wt_path.exists():
        return
    diff = diff_against(task.base_branch, wt_path)
    artifacts.diff_patch.write_text(diff, encoding="utf-8")
    files = git_changed_files(task.base_branch, wt_path)
    artifacts.changed_files.write_text(
        "\n".join(files) + ("\n" if files else ""), encoding="utf-8"
    )


# ---- validation -------------------------------------------------------------


def run_validation(
    project: Project, task: TaskConfig, artifacts: TaskArtifacts
) -> list[CommandResult]:
    """Run task.validation.commands inside the worktree, append to validation.log."""
    if not task.worktree_path:
        raise RuntimeError(
            f"Task {task.id} has no worktree yet. Run `ergon implement` first."
        )
    wt_path = Path(task.worktree_path)
    results: list[CommandResult] = []
    artifacts.validation_log.parent.mkdir(parents=True, exist_ok=True)
    with artifacts.validation_log.open("a", encoding="utf-8") as logf:
        logf.write(f"\n# Validation run @ {datetime.now().isoformat(timespec='seconds')}\n")
        if not task.validation.commands:
            logf.write("(no validation commands configured)\n")
            return results
        for cmd in task.validation.commands:
            logf.write(f"\n$ {cmd}\n")
            result = run_shell(cmd, cwd=wt_path, timeout=900)
            logf.write(result.stdout)
            if result.stderr:
                logf.write("\n[stderr]\n")
                logf.write(result.stderr)
            logf.write(f"\n[exit {result.exit_code}]\n")
            results.append(result)
    return results


# ---- public flows -----------------------------------------------------------


def implement(
    project: Project,
    task_id: str,
    agent_name: str,
    extra_prompt: str | None = None,
) -> tuple[TaskConfig, TaskArtifacts, AgentInvocation]:
    task, artifacts = load_task(project, task_id)
    task = update_status(artifacts, "implementing")

    registry = AgentRegistry()
    agent = registry.get(agent_name)
    wt = ensure_worktree(project, task, artifacts, agent_name)

    prompt = _implementer_prompt(project, task, artifacts, extra_prompt)
    log_path = artifacts.root / f"implementation-{agent_name}.log"
    invocation = make_invocation(
        agent_name=agent_name,
        role="implementer",
        cwd=wt.path,
        prompt=prompt,
        log_path=log_path,
    )

    if agent.definition.mode == "native":
        invocation = agent.run_native(invocation)
    else:
        invocation = agent.run_controlled(invocation)

    capture_diff(project, task, artifacts)

    artifacts.append_text(
        "implementation-log.md",
        f"""

## Run @ {invocation.started_at.isoformat(timespec='seconds')} ({agent_name})

- Mode: {agent.definition.mode}
- Worktree: `{wt.path}`
- Branch: `{wt.branch}`
- Exit: {invocation.exit_code}
- Log: `{log_path.relative_to(artifacts.root)}`
""",
    )
    return task, artifacts, invocation


def _implementer_prompt(
    project: Project,
    task: TaskConfig,
    artifacts: TaskArtifacts,
    extra: str | None,
) -> str:
    brief = _safe_read(artifacts.brief_md)
    context = _safe_read(artifacts.context_md)
    plan = _safe_read(artifacts.plan_md) if artifacts.plan_md.exists() else ""

    extra_section = f"\n## Additional instructions\n\n{extra}\n" if extra else ""
    plan_section = f"\n## Plan\n\n{plan}\n" if plan.strip() else ""
    return f"""You are the implementer agent for project {project.config.name}.
Implement task {task.id}: {task.title} in this worktree.

Stay within ERGON_CONSTRAINTS.md. Prefer small, understandable changes.
When you believe you are done, summarise what you changed and which
validation commands you ran.

## Brief

{brief}

## Context

{context}
{plan_section}{extra_section}"""


def _safe_read(path: Path) -> str:
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


# ---- role flows: plan / review / analyze / debug / summarize ---------------


def plan(
    project: Project, task_id: str, agent_name: str
) -> tuple[TaskConfig, TaskArtifacts, AgentInvocation]:
    task, artifacts = load_task(project, task_id)
    task = update_status(artifacts, "planning")
    agent = AgentRegistry().get(agent_name)

    prompt = role_prompts.planner_prompt(
        project_name=project.config.name,
        project_type=project.config.type,
        brief=_safe_read(artifacts.brief_md),
        context=_safe_read(artifacts.context_md),
        memory_snippets=role_prompts.memory_snippets(project.root),
    )
    log_path = artifacts.root / f"plan-{agent_name}.log"
    invocation = make_invocation(
        agent_name=agent_name,
        role="planner",
        cwd=project.root,
        prompt=prompt,
        log_path=log_path,
    )
    invocation = agent.run_controlled(invocation)
    artifacts.write_text("plan.md", invocation.output)
    return task, artifacts, invocation


def review_one(
    project: Project, task_id: str, agent_name: str, focus: str | None = None
) -> tuple[TaskConfig, TaskArtifacts, AgentInvocation]:
    task, artifacts = load_task(project, task_id)
    agent = AgentRegistry().get(agent_name)

    diff = _safe_read(artifacts.diff_patch)
    if not diff.strip():
        # Refresh diff from worktree if possible.
        capture_diff(project, task, artifacts)
        diff = _safe_read(artifacts.diff_patch)

    prompt = role_prompts.reviewer_prompt(
        project_name=project.config.name,
        task_title=task.title,
        brief=_safe_read(artifacts.brief_md),
        plan=_safe_read(artifacts.plan_md),
        diff=diff,
        validation_log=_safe_read(artifacts.validation_log),
        memory_snippets=role_prompts.memory_snippets(project.root),
        reviewer_focus=focus,
    )
    log_path = artifacts.root / f"review-{agent_name}.log"
    invocation = make_invocation(
        agent_name=agent_name,
        role="reviewer",
        cwd=project.root,
        prompt=prompt,
        log_path=log_path,
    )
    invocation = agent.run_controlled(invocation)
    artifacts.write_text(f"review-{agent_name}.md", invocation.output)
    return task, artifacts, invocation


def review(
    project: Project, task_id: str, agent_names: list[str]
) -> tuple[TaskConfig, TaskArtifacts, list[AgentInvocation]]:
    task, artifacts = load_task(project, task_id)
    task = update_status(artifacts, "reviewing")
    invocations: list[AgentInvocation] = []
    for name in agent_names:
        _, _, inv = review_one(project, task_id, name)
        invocations.append(inv)

    # Stitch reviews into a summary file (no agent — just concatenation).
    parts: list[str] = [f"# Review summary for task {task.id}: {task.title}\n"]
    for inv in invocations:
        parts.append(f"\n## Review by {inv.agent_name}\n\n{inv.output}\n")
    artifacts.write_text("review-summary.md", "".join(parts))
    return task, artifacts, invocations


def analyze(
    project: Project | None,
    target: Path,
    input_kind: str,
    agent_name: str,
    task_id: str | None = None,
    max_chars: int = 60_000,
) -> tuple[TaskArtifacts | None, AgentInvocation]:
    """Run the analyzer agent against a single file.

    If `task_id` is provided, the result is also written into that task's
    folder; otherwise it is written next to the target.
    """
    excerpt = _read_target_excerpt(target, max_chars)
    project_name = project.config.name if project else None
    prompt = role_prompts.analyzer_prompt(
        input_kind=input_kind,
        input_excerpt=excerpt,
        project_name=project_name,
    )
    agent = AgentRegistry().get(agent_name)

    artifacts: TaskArtifacts | None = None
    if project and task_id:
        _, artifacts = load_task(project, task_id)
        log_path = artifacts.root / f"analyze-{agent_name}.log"
        cwd = artifacts.root
    else:
        log_path = target.parent / f"analyze-{agent_name}.log"
        cwd = target.parent

    invocation = make_invocation(
        agent_name=agent_name,
        role="analyzer",
        cwd=cwd,
        prompt=prompt,
        log_path=log_path,
    )
    invocation = agent.run_controlled(invocation)

    if artifacts:
        artifacts.write_text(f"analyze-{agent_name}.md", invocation.output)
    else:
        out = target.parent / f"{target.stem}.analysis-{agent_name}.md"
        out.write_text(invocation.output, encoding="utf-8")
    return artifacts, invocation


def _read_target_excerpt(target: Path, max_chars: int) -> str:
    if not target.exists():
        raise FileNotFoundError(f"No such file: {target}")
    if target.is_dir():
        # Concatenate small text files within the directory.
        chunks: list[str] = []
        budget = max_chars
        for p in sorted(target.rglob("*")):
            if p.is_dir() or budget <= 0:
                continue
            try:
                body = p.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            chunk = f"\n\n----- {p.relative_to(target)} -----\n{body[:budget]}"
            chunks.append(chunk)
            budget -= len(chunk)
        return "".join(chunks)[:max_chars]
    try:
        body = target.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return f"(unable to read {target} as text — binary file?)"
    if len(body) > max_chars:
        body = body[:max_chars] + f"\n\n[...truncated, {len(body) - max_chars} more chars]"
    return body


def debug(
    project: Project, task_id: str, agent_name: str, extra_logs: str = ""
) -> tuple[TaskConfig, TaskArtifacts, AgentInvocation]:
    task, artifacts = load_task(project, task_id)
    agent = AgentRegistry().get(agent_name)

    diff = _safe_read(artifacts.diff_patch)
    if not diff.strip() and task.worktree_path:
        capture_diff(project, task, artifacts)
        diff = _safe_read(artifacts.diff_patch)

    prompt = role_prompts.debugger_prompt(
        task_title=task.title,
        brief=_safe_read(artifacts.brief_md),
        diff=diff,
        validation_log=_safe_read(artifacts.validation_log),
        extra_logs=extra_logs,
    )
    log_path = artifacts.root / f"debug-{agent_name}.log"
    invocation = make_invocation(
        agent_name=agent_name,
        role="debugger",
        cwd=project.root,
        prompt=prompt,
        log_path=log_path,
    )
    invocation = agent.run_controlled(invocation)
    artifacts.write_text(f"debug-{agent_name}.md", invocation.output)
    return task, artifacts, invocation
