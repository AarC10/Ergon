"""Prompt builders for controlled-mode role agents.

Each function returns a single string prompt suitable for piping to a model
CLI on stdin. They keep the agent on a tight rail: input sections, output
schema, and a short directive about what the agent should *not* do.
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable


def _section(title: str, body: str) -> str:
    body = body.rstrip()
    return f"## {title}\n\n{body}\n" if body else ""


def _read(path: Path | None) -> str:
    if path is None or not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def planner_prompt(
    project_name: str,
    project_type: str,
    brief: str,
    context: str,
    memory_snippets: Iterable[str] = (),
) -> str:
    memory = "\n\n---\n\n".join(s.strip() for s in memory_snippets if s.strip())
    return (
        f"You are the planner agent for project {project_name} ({project_type}).\n"
        "Produce a focused implementation plan for the task below. Do not write\n"
        "production code. Output Markdown with these sections:\n\n"
        "  1. Summary\n"
        "  2. Affected files (bullet list with one-line reasons)\n"
        "  3. Implementation steps (numbered, each independently reviewable)\n"
        "  4. Risks (bullet list — what could go wrong, blast radius)\n"
        "  5. Validation plan (commands the implementer should run)\n\n"
        "Stay within the constraints described. Prefer the smallest plan that\n"
        "actually solves the goal.\n\n"
        + _section("Task brief", brief)
        + _section("Context", context)
        + _section("Project memory", memory)
    )


def reviewer_prompt(
    project_name: str,
    task_title: str,
    brief: str,
    plan: str,
    diff: str,
    validation_log: str,
    memory_snippets: Iterable[str] = (),
    reviewer_focus: str | None = None,
) -> str:
    memory = "\n\n---\n\n".join(s.strip() for s in memory_snippets if s.strip())
    focus = (
        f"Special focus for this review: {reviewer_focus}.\n"
        if reviewer_focus
        else ""
    )
    return (
        f"You are a reviewer for project {project_name}. Review the diff against\n"
        f"the task brief, plan, and validation log. {focus}"
        "Output Markdown with these sections:\n\n"
        "  1. Summary (2-4 sentences)\n"
        "  2. Blocking issues (must fix — file:line where possible)\n"
        "  3. Important issues (should fix)\n"
        "  4. Optional improvements (nice to have)\n"
        "  5. Test coverage notes\n\n"
        "Do not rewrite code. Reference exact files and lines.\n\n"
        f"Task: {task_title}\n\n"
        + _section("Brief", brief)
        + _section("Plan", plan)
        + _section("Diff", diff)
        + _section("Validation log", validation_log)
        + _section("Project memory", memory)
    )


def analyzer_prompt(
    input_kind: str,
    input_excerpt: str,
    project_name: str | None = None,
) -> str:
    project_line = f" for project {project_name}" if project_name else ""
    return (
        f"You are an analyzer agent{project_line}. Interpret the {input_kind} below.\n"
        "Separate evidence from inference. Do not invent facts not visible in the\n"
        "input. Output Markdown with these sections:\n\n"
        "  1. Observations (what you see, with quoted evidence)\n"
        "  2. Findings (interpretations, marked low/medium/high confidence)\n"
        "  3. Risks\n"
        "  4. Suggested follow-up tasks (one bullet per task, with a one-line goal)\n\n"
        + _section("Input", input_excerpt)
    )


def debugger_prompt(
    task_title: str,
    brief: str,
    diff: str,
    validation_log: str,
    extra_logs: str = "",
) -> str:
    return (
        "You are a debugging agent. Identify the most likely root cause of the\n"
        "failure described below and propose a single recommended fix path.\n"
        "Output Markdown with these sections:\n\n"
        "  1. Symptom (what was observed)\n"
        "  2. Root cause hypothesis (ranked, top one with strongest evidence)\n"
        "  3. Evidence for/against each hypothesis\n"
        "  4. Recommended fix (specific file/function changes)\n"
        "  5. Test plan (how the implementer can verify the fix)\n\n"
        f"Task: {task_title}\n\n"
        + _section("Brief", brief)
        + _section("Recent diff", diff)
        + _section("Validation log", validation_log)
        + _section("Extra logs", extra_logs)
    )


def summarizer_prompt(
    project_name: str,
    task_title: str,
    diff: str,
    validation_log: str,
    review_summary: str,
) -> str:
    return (
        f"You are the summariser for project {project_name}.\n"
        f"Produce a final human-readable summary of task '{task_title}'. Output\n"
        "Markdown with these sections:\n\n"
        "  1. What changed\n"
        "  2. Validation status\n"
        "  3. Review status\n"
        "  4. Risks remaining\n"
        "  5. Suggested next steps\n\n"
        "Be concise. No fluff.\n\n"
        + _section("Diff", diff)
        + _section("Validation log", validation_log)
        + _section("Review summary", review_summary)
    )


# Convenience: read project memory files for inclusion in prompts.


def memory_snippets(project_root: Path) -> list[str]:
    mem = project_root / ".ergon" / "memory"
    if not mem.is_dir():
        return []
    out: list[str] = []
    for fname in ("architecture.md", "decisions.md", "conventions.md", "glossary.md"):
        path = mem / fname
        body = _read(path).strip()
        if body:
            out.append(f"### {fname}\n\n{body}")
    return out
