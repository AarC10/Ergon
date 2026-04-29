from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Iterator

from ergon.agents.base import (
    Agent,
    AgentExecutionError,
    AgentInvocation,
    AgentNotAvailable,
    assert_command_available,
)
from ergon.agents.registry import AgentRegistry
from ergon.core.artifact_store import TaskArtifacts
from ergon.core.config import (
    AgentsConfig,
    REVIEWER_ROLE_NAMES,
    ROLE_NAMES,
    ProjectAgents,
    RoleRoute,
    TaskConfig,
)
from ergon.core.project import Project
from ergon.core.task import create_task, load_task, preview_task, update_status
from ergon.roles import prompts as role_prompts
from ergon.tools.commands import CommandResult, run_shell
from ergon.tools.git import changed_files as git_changed_files
from ergon.tools.git import diff_against
from ergon.tools.worktree import Worktree, create_worktree
from ergon.utils.slug import slugify_identifier


class ReviewPreconditionError(RuntimeError):
    """Raised when a review is requested for a task with nothing to review."""


class SafetyViolation(RuntimeError):
    """Raised when an agent's mode conflicts with the active safety level."""


class RunTargetError(RuntimeError):
    """Raised when `ergon run` cannot resolve its target argument."""


@dataclass
class RunStep:
    name: str
    outcome: str
    detail: str = ""


@dataclass
class RunPipelineResult:
    project_root: Path
    task_id: str
    task_title: str
    task_status: str
    created: bool
    dry_run: bool
    planner_agent: str
    planner_source: str
    implementer_agent: str
    implementer_source: str
    reviewer_agents: list[str]
    reviewer_sources: list[str] = field(default_factory=list)
    summarizer_agent: str | None = None
    summarizer_source: str | None = None
    steps: list[RunStep] = field(default_factory=list)
    summary_path: Path | None = None
    stopped_reason: str | None = None
    validation_failed: bool = False


@dataclass
class RoleResolution:
    role_name: str
    selected_agent: str
    source: str
    fallback_candidates: list[str] = field(default_factory=list)
    candidate_chain: list[str] = field(default_factory=list)


# ---- agent + safety preflight ----------------------------------------------


def _resolve_agent(registry: AgentRegistry, agent_name: str) -> Agent:
    """Look up an agent and verify its CLI is on PATH.

    Both errors raise AgentNotAvailable so callers can present a single
    user-facing failure mode.
    """
    if not agent_name:
        raise AgentNotAvailable("No agent specified.")
    sanitized = slugify_identifier(agent_name)
    if sanitized != agent_name:
        raise AgentNotAvailable(
            f"Agent name {agent_name!r} contains characters that aren't safe "
            f"for filesystem / git use. Try {sanitized!r} or rename in agents.yaml."
        )
    agent = registry.get(agent_name)
    assert_command_available(agent.definition)
    return agent


def _enforce_safety(safety: str, agent: Agent) -> None:
    """Apply the minimum safety contract for the MVP.

    - strict: no native CLI execution. Agent must be controlled-mode.
    - guarded: native CLI is fine; Ergon already restricts it to the worktree.
      No merge/push commands are ever run by Ergon.
    - unsafe: native CLI is allowed; safety contract is "we still capture
      logs and diffs, but the user accepted broader command access".
    - unrestricted: anything goes; this should only ever be reached via an
      explicit `--dangerously-unrestricted` flag at the call site.
    """
    if safety == "strict" and agent.definition.mode == "native":
        raise SafetyViolation(
            f"Safety level 'strict' refuses native CLI execution. "
            f"Agent '{agent.name}' is configured mode=native. "
            f"Switch the project to 'guarded' or use a controlled-mode agent."
        )


# ---- status hygiene --------------------------------------------------------


@contextmanager
def _phase(
    artifacts: TaskArtifacts,
    in_progress: str,
    success: str,
) -> Iterator[TaskConfig]:
    """Bracket a phase with status transitions.

    Sets `in_progress` on entry, `success` on clean exit, `failed` on
    exception (and re-raises). The fresh task is yielded.
    """
    prior = artifacts.load_task().status
    task = update_status(artifacts, in_progress)
    try:
        yield task
    except Exception:
        try:
            update_status(artifacts, "failed")
        except Exception:
            pass
        # Best-effort: don't lose the original error if status save also fails.
        raise
    else:
        # Don't downgrade a task that's already moved past `success` (e.g. if
        # the agent's run_native callback updated status itself).
        update_status(artifacts, success)


# ---- worktree-bound task setup ---------------------------------------------


def ensure_worktree(
    project: Project,
    task: TaskConfig,
    artifacts: TaskArtifacts,
    agent: str,
) -> Worktree:
    """Create or reuse the worktree for (task, agent), and update task.yaml."""
    agent_id = slugify_identifier(agent)
    repo_id = slugify_identifier(project.config.name)
    if not agent_id or not repo_id:
        raise ValueError(
            "Repo name and agent name must contain at least one slug-safe "
            "character (letters, digits, dashes)."
        )
    wt = create_worktree(
        repo_root=project.root,           # authoritative — not stale config
        repo_name=repo_id,
        task_id=task.id,
        slug=task.slug,
        agent=agent_id,
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
Safety level: {task.safety_level}

## Constraints

{constraints}

## Validation

Run these commands before declaring done:

{validation}

## What Ergon will not do for you

- Merge or push branches.
- Run commands outside this worktree.
- Override the forbidden_paths above.
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
    if not wt_path.exists():
        raise RuntimeError(
            f"Worktree for task {task.id} no longer exists at {wt_path}."
        )
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


def validate(
    project: Project, task_id: str
) -> tuple[TaskConfig, TaskArtifacts, list[CommandResult]]:
    """Public entry point for `ergon validate` with proper status hygiene."""
    task, artifacts = load_task(project, task_id)
    if not task.worktree_path:
        raise RuntimeError(
            f"Task {task.id} has no worktree yet. Run `ergon implement` first."
        )
    with _phase(artifacts, "validating", "validated") as task:
        results = run_validation(project, task, artifacts)
    if any(not r.ok for r in results):
        task = update_status(artifacts, "failed")
    else:
        task = artifacts.load_task()
    return task, artifacts, results


# ---- public flows -----------------------------------------------------------


def implement(
    project: Project,
    task_id: str,
    agent_name: str,
    extra_prompt: str | None = None,
) -> tuple[TaskConfig, TaskArtifacts, AgentInvocation]:
    task, artifacts = load_task(project, task_id)
    registry = AgentRegistry()
    agent = _resolve_agent(registry, agent_name)
    _enforce_safety(task.safety_level, agent)

    with _phase(artifacts, "implementing", "implemented") as task:
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
        if invocation.exit_code != 0:
            raise AgentExecutionError(
                f"Implementer {agent_name} exited with code {invocation.exit_code}. "
                f"See {log_path.relative_to(artifacts.root)}."
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
    agent = _resolve_agent(AgentRegistry(), agent_name)

    with _phase(artifacts, "planning", "planned") as task:
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
    agent = _resolve_agent(AgentRegistry(), agent_name)

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

    # P0-3: refuse to "review" tasks that have no implementation. We will not
    # produce an authoritative-looking review-summary.md for nothing.
    if not task.worktree_path:
        raise ReviewPreconditionError(
            f"Task {task.id} has no worktree. Run `ergon implement` first."
        )
    wt_path = Path(task.worktree_path)
    if not wt_path.exists():
        raise ReviewPreconditionError(
            f"Worktree for task {task.id} no longer exists at {wt_path}."
        )

    # Refresh the diff against the actual worktree before deciding emptiness.
    capture_diff(project, task, artifacts)
    diff_text = _safe_read(artifacts.diff_patch).strip()
    if not diff_text:
        raise ReviewPreconditionError(
            f"Task {task.id} has an empty diff. Nothing to review."
        )

    # Pre-validate every reviewer agent before changing status.
    registry = AgentRegistry()
    for name in agent_names:
        _resolve_agent(registry, name)

    with _phase(artifacts, "reviewing", "reviewed") as task:
        invocations: list[AgentInvocation] = []
        for name in agent_names:
            _, _, inv = review_one(project, task_id, name)
            invocations.append(inv)
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
    excerpt = _read_target_excerpt(target, max_chars)
    project_name = project.config.name if project else None
    prompt = role_prompts.analyzer_prompt(
        input_kind=input_kind,
        input_excerpt=excerpt,
        project_name=project_name,
    )
    agent = _resolve_agent(AgentRegistry(), agent_name)

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
    agent = _resolve_agent(AgentRegistry(), agent_name)

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


# ---- agent default resolution ----------------------------------------------


_LEGACY_ROLE_FIELDS: dict[str, str] = {
    "planner": "planner",
    "implementer": "implementer",
    "debugger": "debugger",
    "analyzer": "analyzer",
    "analyzer_multimodal": "analyzer",
}


def resolve_agent_choice(
    explicit: str | None,
    task: TaskConfig | None,
    project: Project,
    role: str,
    fallback: str,
) -> str:
    """Legacy string-only wrapper around the role resolver.

    This keeps older callers working while newer code can use `resolve_role`
    to obtain the selected agent plus source/fallback metadata.
    """
    return resolve_role(
        role_name=role,
        explicit_agent=explicit,
        task=task,
        project=project,
        builtin_fallback=fallback,
        require_command=True,
    ).selected_agent


def resolve_role(
    role_name: str,
    explicit_agent: str | None = None,
    task: TaskConfig | None = None,
    project: Project | None = None,
    allow_fallback: bool = True,
    allow_escalation: bool = False,
    builtin_fallback: str | None = None,
    global_config: AgentsConfig | None = None,
    require_command: bool = False,
) -> RoleResolution:
    """Resolve a role to an agent alias plus source metadata.

    Priority:
    1. explicit CLI override
    2. task.yaml role mapping / legacy task.agents
    3. project.yaml role mapping / legacy project.agents
    4. global ~/.ergon/agents.yaml role mapping
    5. built-in defaults
    """
    if explicit_agent:
        return RoleResolution(
            role_name=role_name,
            selected_agent=explicit_agent,
            source="explicit CLI override",
            candidate_chain=[explicit_agent],
        )

    global_cfg = global_config or AgentsConfig.load()
    known_roles = set(ROLE_NAMES) | set(_LEGACY_ROLE_FIELDS) | set(REVIEWER_ROLE_NAMES)
    if role_name not in known_roles:
        raise ValueError(
            f"Unknown role '{role_name}'. Known roles: {', '.join(sorted(known_roles))}"
        )

    available_agents = set(global_cfg.agents)

    if task is not None:
        route = task.roles.get(role_name)
        if route is not None:
            return _resolve_from_route(
                role_name=role_name,
                route=route,
                source_prefix=f"task.yaml roles.{role_name}",
                available_agents=available_agents,
                agent_defs=global_cfg.agents,
                allow_fallback=allow_fallback,
                allow_escalation=allow_escalation,
                require_command=require_command,
            )
        legacy = _legacy_role_agent(task.agents, role_name)
        if legacy:
            return RoleResolution(
                role_name=role_name,
                selected_agent=legacy,
                source=f"task.yaml agents.{_legacy_role_field_name(role_name)}",
                candidate_chain=[legacy],
            )

    if project is not None:
        route = project.config.roles.get(role_name)
        if route is not None:
            return _resolve_from_route(
                role_name=role_name,
                route=route,
                source_prefix=f"project.yaml roles.{role_name}",
                available_agents=available_agents,
                agent_defs=global_cfg.agents,
                allow_fallback=allow_fallback,
                allow_escalation=allow_escalation,
                require_command=require_command,
            )
        legacy = _legacy_role_agent(project.config.agents, role_name)
        if legacy:
            return RoleResolution(
                role_name=role_name,
                selected_agent=legacy,
                source=f"project.yaml agents.{_legacy_role_field_name(role_name)}",
                candidate_chain=[legacy],
            )

    route = global_cfg.roles.get(role_name)
    if route is not None:
        return _resolve_from_route(
            role_name=role_name,
            route=route,
            source_prefix=f"~/.ergon/agents.yaml roles.{role_name}",
            available_agents=available_agents,
            agent_defs=global_cfg.agents,
            allow_fallback=allow_fallback,
            allow_escalation=allow_escalation,
            require_command=require_command,
        )

    builtin_route = AgentsConfig.default_roles().get(role_name)
    if builtin_route is not None:
        return _resolve_from_route(
            role_name=role_name,
            route=builtin_route,
            source_prefix=f"built-in defaults roles.{role_name}",
            available_agents=available_agents,
            agent_defs=global_cfg.agents,
            allow_fallback=allow_fallback,
            allow_escalation=allow_escalation,
            require_command=require_command,
        )

    if builtin_fallback:
        return RoleResolution(
            role_name=role_name,
            selected_agent=builtin_fallback,
            source=f"legacy fallback {builtin_fallback!r}",
            candidate_chain=[builtin_fallback],
        )
    raise ValueError(f"No mapping found for role '{role_name}'.")


def _agent_from(agents: object, role: str) -> str | None:
    """Pull a single agent name out of a ProjectAgents-like object for a role.

    For `reviewers` (a list), returns the first non-empty entry.
    """
    val = getattr(agents, role, None)
    if isinstance(val, str) and val.strip():
        return val
    if isinstance(val, list) and val:
        for entry in val:
            if isinstance(entry, str) and entry.strip():
                return entry
    return None


def _legacy_role_agent(agents: ProjectAgents, role_name: str) -> str | None:
    field_name = _legacy_role_field_name(role_name)
    if field_name is None:
        return None
    return _agent_from(agents, field_name)


def _legacy_role_field_name(role_name: str) -> str | None:
    if role_name in REVIEWER_ROLE_NAMES:
        return "reviewers"
    return _LEGACY_ROLE_FIELDS.get(role_name)


def _resolve_from_route(
    role_name: str,
    route: RoleRoute,
    source_prefix: str,
    available_agents: set[str],
    agent_defs: dict[str, object],
    allow_fallback: bool,
    allow_escalation: bool,
    require_command: bool,
) -> RoleResolution:
    candidates: list[tuple[str, str]] = []
    if allow_escalation and route.escalation:
        candidates.append((route.escalation, "escalation"))
    if route.primary:
        candidates.append((route.primary, "primary"))
    if allow_fallback and route.fallback:
        candidates.append((route.fallback, "fallback"))
    if not candidates:
        raise ValueError(
            f"Role '{role_name}' has no usable mapping under {source_prefix}."
        )

    missing: list[str] = []
    selected_agent: str | None = None
    selected_kind: str | None = None
    for agent_name, kind in candidates:
        if agent_name not in available_agents:
            missing.append(agent_name)
            continue
        if require_command and not _command_exists_for(agent_name, agent_defs):
            missing.append(f"{agent_name} (CLI unavailable)")
            continue
        if agent_name in available_agents:
            selected_agent = agent_name
            selected_kind = kind
            break

    if selected_agent is None:
        names = ", ".join(agent for agent, _ in candidates)
        raise ValueError(
            f"Role '{role_name}' could not resolve to a runnable agent under "
            f"{source_prefix}: {names}. Configure them in ~/.ergon/agents.yaml."
        )

    source = f"{source_prefix}.{selected_kind}"
    if missing:
        source += f" (after missing {', '.join(missing)})"

    remaining = [
        agent
        for agent, _ in candidates
        if agent != selected_agent and agent in available_agents
    ]
    return RoleResolution(
        role_name=role_name,
        selected_agent=selected_agent,
        source=source,
        fallback_candidates=remaining,
        candidate_chain=[agent for agent, _ in candidates],
    )


def _command_exists_for(agent_name: str, agent_defs: dict[str, object]) -> bool:
    definition = agent_defs.get(agent_name)
    if definition is None:
        return False
    command = getattr(definition, "command", None)
    if not isinstance(command, str) or not command:
        return False
    return which(command) is not None


def resolve_role_or_raise(
    role_name: str,
    *,
    project: Project | None = None,
    task: TaskConfig | None = None,
    explicit_agent: str | None = None,
    allow_fallback: bool = True,
    allow_escalation: bool = False,
    builtin_fallback: str | None = None,
    require_command: bool = True,
) -> RoleResolution:
    return resolve_role(
        role_name=role_name,
        explicit_agent=explicit_agent,
        task=task,
        project=project,
        allow_fallback=allow_fallback,
        allow_escalation=allow_escalation,
        builtin_fallback=builtin_fallback,
        require_command=require_command,
    )


def resolve_reviewers(
    explicit: list[str] | None,
    task: TaskConfig | None,
    project: Project,
    fallback: list[str],
) -> list[str]:
    if explicit:
        return [e for e in explicit if e.strip()]
    if task is not None and task.agents.reviewers:
        return list(task.agents.reviewers)
    if project.config.agents.reviewers:
        return list(project.config.agents.reviewers)
    return [
        res.selected_agent
        for res in resolve_reviewer_roles(
            task=task,
            project=project,
            fallback=fallback,
            require_command=True,
        )
    ]


def resolve_reviewer_roles(
    task: TaskConfig | None,
    project: Project | None,
    fallback: list[str],
    explicit: list[str] | None = None,
    require_command: bool = False,
) -> list[RoleResolution]:
    if explicit:
        return [
            RoleResolution(
                role_name="explicit reviewer override",
                selected_agent=agent,
                source="explicit CLI override",
                candidate_chain=[agent],
            )
            for agent in explicit
            if agent.strip()
        ]
    if task is not None and task.agents.reviewers:
        return [
            RoleResolution(
                role_name="legacy reviewers",
                selected_agent=agent,
                source="task.yaml agents.reviewers",
                candidate_chain=[agent],
            )
            for agent in task.agents.reviewers
        ]
    if project is not None and project.config.agents.reviewers:
        return [
            RoleResolution(
                role_name="legacy reviewers",
                selected_agent=agent,
                source="project.yaml agents.reviewers",
                candidate_chain=[agent],
            )
            for agent in project.config.agents.reviewers
        ]

    resolutions: list[RoleResolution] = []
    for role_name in REVIEWER_ROLE_NAMES:
        try:
            resolutions.append(
                resolve_role(
                    role_name=role_name,
                    task=task,
                    project=project,
                    builtin_fallback=fallback[0] if fallback else None,
                    require_command=require_command,
                )
            )
        except ValueError:
            continue
    if not resolutions and fallback:
        return [
            RoleResolution(
                role_name="legacy reviewer fallback",
                selected_agent=agent,
                source="legacy fallback",
                candidate_chain=[agent],
            )
            for agent in fallback
        ]

    deduped: list[RoleResolution] = []
    seen: set[str] = set()
    for resolution in resolutions:
        if resolution.selected_agent in seen:
            continue
        seen.add(resolution.selected_agent)
        deduped.append(resolution)
    return deduped


# ---- run pipeline -----------------------------------------------------------


def run_pipeline(
    project: Project,
    target: str,
    implementer: str | None = None,
    planner: str | None = None,
    reviewers: list[str] | None = None,
    escalate: bool = False,
    skip_plan: bool = False,
    skip_validate: bool = False,
    skip_review: bool = False,
    force: bool = False,
    dry_run: bool = False,
) -> RunPipelineResult:
    task, artifacts, created = _resolve_run_target(project, target, dry_run=dry_run)

    planner_resolution = resolve_role_or_raise(
        role_name="planner",
        explicit_agent=planner,
        task=task,
        project=project,
        builtin_fallback="openai",
        require_command=True,
    )
    implementer_resolution = resolve_role_or_raise(
        role_name="implementer",
        explicit_agent=implementer,
        task=task,
        project=project,
        allow_escalation=escalate,
        builtin_fallback="claude",
        require_command=True,
    )
    reviewer_resolutions = [] if skip_review else resolve_reviewer_roles(
        explicit=reviewers,
        task=task,
        project=project,
        fallback=["openai"],
        require_command=True,
    )
    summarizer_resolution = resolve_role(
        role_name="summarizer",
        task=task,
        project=project,
        builtin_fallback="haiku-4.5",
        require_command=True,
    )

    planner_agent = planner_resolution.selected_agent
    implementer_agent = implementer_resolution.selected_agent
    reviewer_agents = [resolution.selected_agent for resolution in reviewer_resolutions]

    result = RunPipelineResult(
        project_root=project.root,
        task_id=task.id,
        task_title=task.title,
        task_status=task.status,
        created=created,
        dry_run=dry_run,
        planner_agent=planner_agent,
        planner_source=planner_resolution.source,
        implementer_agent=implementer_agent,
        implementer_source=implementer_resolution.source,
        reviewer_agents=reviewer_agents,
        reviewer_sources=[resolution.source for resolution in reviewer_resolutions],
        summarizer_agent=summarizer_resolution.selected_agent,
        summarizer_source=summarizer_resolution.source,
        summary_path=None if dry_run else artifacts.run_summary,
    )

    needs_plan = _needs_plan(task, artifacts, force)
    needs_implement = _needs_implement(task, artifacts, force)
    needs_validate = _needs_validate(task, artifacts, force, needs_implement)
    needs_review = _needs_review(task, artifacts, force, needs_validate)

    actions = [
        (
            "plan",
            not skip_plan,
            planner_agent,
            needs_plan,
        ),
        (
            "implement",
            True,
            implementer_agent,
            needs_implement,
        ),
        (
            "validate",
            not skip_validate,
            None,
            needs_validate,
        ),
        (
            "review",
            not skip_review,
            ", ".join(reviewer_agents) if reviewer_agents else None,
            needs_review,
        ),
    ]

    if dry_run:
        for name, enabled, actor, needed in actions:
            detail = actor or "default"
            if not enabled:
                result.steps.append(RunStep(name, "skipped", "flagged off"))
            elif needed:
                result.steps.append(RunStep(name, "would-run", detail))
            else:
                result.steps.append(RunStep(name, "skipped", "already complete"))
        return result

    try:
        for name, enabled, actor, needed in actions:
            if not enabled:
                result.steps.append(RunStep(name, "skipped", "flagged off"))
                continue
            if not needed:
                result.steps.append(RunStep(name, "skipped", "already complete"))
                continue

            try:
                if name == "plan":
                    _, artifacts, invocation = plan(project, task.id, planner_agent)
                    result.steps.append(
                        RunStep(name, "ran", f"{planner_agent} exit={invocation.exit_code}")
                    )
                elif name == "implement":
                    _, artifacts, invocation = implement(
                        project, task.id, implementer_agent, None
                    )
                    result.steps.append(
                        RunStep(
                            name,
                            "ran",
                            f"{implementer_agent} exit={invocation.exit_code}",
                        )
                    )
                elif name == "validate":
                    _, artifacts, results = validate(project, task.id)
                    failed = [r for r in results if not r.ok]
                    if failed:
                        result.steps.append(
                            RunStep(name, "failed", f"{len(failed)}/{len(results)} commands")
                        )
                        result.validation_failed = True
                        result.stopped_reason = "validation failed"
                        break
                    if not results:
                        result.steps.append(RunStep(name, "ran", "no commands configured"))
                    else:
                        result.steps.append(
                            RunStep(name, "ran", f"{len(results)} command(s) passed")
                        )
                elif name == "review":
                    _, artifacts, invocations = review(project, task.id, reviewer_agents)
                    failed = [i for i in invocations if i.exit_code not in (0, None)]
                    detail = (
                        f"{len(failed)}/{len(invocations)} reviewers non-zero"
                        if failed else f"{len(invocations)} reviewer(s)"
                    )
                    result.steps.append(RunStep(name, "ran", detail))
            except Exception as e:
                result.steps.append(RunStep(name, "failed", str(e)))
                raise

            task = artifacts.load_task()
    except Exception as e:
        result.stopped_reason = str(e)
    finally:
        if artifacts.root.exists():
            final_task = artifacts.load_task()
            result.task_status = final_task.status
            _write_run_summary(
                project=project,
                artifacts=artifacts,
                result=result,
                final_task=final_task,
                force=force,
                skip_plan=skip_plan,
                skip_validate=skip_validate,
                skip_review=skip_review,
            )
    return result


def _resolve_run_target(
    project: Project,
    target: str,
    dry_run: bool,
) -> tuple[TaskConfig, TaskArtifacts, bool]:
    try:
        task, artifacts = load_task(project, target)
        return task, artifacts, False
    except FileNotFoundError:
        pass

    if target.isdigit():
        raise RunTargetError(f"No task matching '{target}' under {project.tasks_dir}")

    if dry_run:
        task, artifacts = preview_task(project, title=target)
        return task, artifacts, True

    task, artifacts = create_task(project, title=target)
    return task, artifacts, True


def _needs_plan(task: TaskConfig, artifacts: TaskArtifacts, force: bool) -> bool:
    if force:
        return True
    return not artifacts.plan_md.exists()


def _needs_implement(task: TaskConfig, artifacts: TaskArtifacts, force: bool) -> bool:
    if force:
        return True
    wt_exists = bool(task.worktree_path) and Path(task.worktree_path).exists()
    return not (
        wt_exists
        and task.branch_name
        and artifacts.implementation_log.exists()
    )


def _needs_validate(
    task: TaskConfig,
    artifacts: TaskArtifacts,
    force: bool,
    needs_implement: bool,
) -> bool:
    if force:
        return True
    if needs_implement:
        return True
    if not artifacts.validation_log.exists():
        return True
    return not _last_validation_succeeded(artifacts)


def _needs_review(
    task: TaskConfig,
    artifacts: TaskArtifacts,
    force: bool,
    needs_validate: bool,
) -> bool:
    if force:
        return True
    if needs_validate:
        return True
    return task.status != "reviewed" or not artifacts.review_summary.exists()


def _last_validation_succeeded(artifacts: TaskArtifacts) -> bool:
    try:
        body = artifacts.validation_log.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    if not body.strip():
        return False

    marker = "\n# Validation run @ "
    idx = body.rfind(marker)
    section = body[idx + 1:] if idx != -1 else body
    if "(no validation commands configured)" in section:
        return True

    exit_codes: list[int] = []
    for raw in section.splitlines():
        line = raw.strip()
        if line.startswith("[exit ") and line.endswith("]"):
            try:
                exit_codes.append(int(line[6:-1]))
            except ValueError:
                return False
    return bool(exit_codes) and all(code == 0 for code in exit_codes)


def _write_run_summary(
    project: Project,
    artifacts: TaskArtifacts,
    result: RunPipelineResult,
    final_task: TaskConfig,
    force: bool,
    skip_plan: bool,
    skip_validate: bool,
    skip_review: bool,
) -> None:
    lines = [
        f"# Run summary for task {final_task.id}: {final_task.title}",
        "",
        f"- Generated: {datetime.now().isoformat(timespec='seconds')}",
        f"- Status: {final_task.status}",
        f"- Created by `ergon run`: {result.created}",
        f"- Force: {force}",
        f"- Skip plan / validate / review: {skip_plan} / {skip_validate} / {skip_review}",
        f"- Planner: {result.planner_agent} ({result.planner_source})",
        f"- Implementer: {result.implementer_agent} ({result.implementer_source})",
        "- Reviewers: " + (
            ", ".join(
                f"{agent} ({source})"
                for agent, source in zip(result.reviewer_agents, result.reviewer_sources)
            )
            if result.reviewer_agents else "(none)"
        ),
        "- Summarizer: " + (
            f"{result.summarizer_agent} ({result.summarizer_source})"
            if result.summarizer_agent and result.summarizer_source else "(none)"
        ),
        f"- Worktree: {final_task.worktree_path or '-'}",
        f"- Branch: {final_task.branch_name or '-'}",
        "",
        "## Steps",
        "",
    ]
    for step in result.steps:
        line = f"- {step.name}: {step.outcome}"
        if step.detail:
            line += f" ({step.detail})"
        lines.append(line)
    if result.validation_failed:
        lines.extend(["", "## Outcome", "", "- Stopped after validation failure."])
    elif result.stopped_reason:
        lines.extend(["", "## Outcome", "", f"- Stopped: {result.stopped_reason}"])
    else:
        lines.extend(["", "## Outcome", "", "- Completed without merge or push."])
    artifacts.write_text("run-summary.md", "\n".join(lines) + "\n")
