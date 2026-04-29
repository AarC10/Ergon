from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path
from shutil import which
from typing import Final

from ergon.agents.base import (
    AgentInvocation,
    AgentNotAvailable,
    assert_command_available,
)
from ergon.core.config import AgentDef


# Variables every interactive CLI tends to need. Anything outside this set
# (and the per-agent passthrough list) is *not* forwarded to the subprocess.
_BASE_ENV_KEYS: tuple[str, ...] = (
    "PATH",
    "HOME",
    "USER",
    "USERNAME",
    "LOGNAME",
    "SHELL",
    "TERM",
    "TMPDIR",
    "LANG",
    "LC_ALL",
    "LC_CTYPE",
)


def build_subprocess_env(definition: AgentDef) -> dict[str, str]:
    """Construct a minimal allowlisted environment for an agent subprocess.

    The parent process's full environment is *not* inherited. Only the
    base allowlist plus the agent's declared `env.passthrough` keys are
    copied across. `env.set` overrides anything else.

    This prevents incidental leakage of unrelated API keys or session
    secrets into agent subprocesses.
    """
    parent = os.environ
    env: dict[str, str] = {}
    for key in _BASE_ENV_KEYS:
        val = parent.get(key)
        if val is not None:
            env[key] = val
    for key in definition.env.passthrough:
        val = parent.get(key)
        if val is not None:
            env[key] = val
    env.update(definition.env.set)
    return env


class CliAgent:
    """Generic adapter that fronts an AI CLI binary (claude, codex, gemini, ...)."""

    def __init__(self, name: str, definition: AgentDef):
        self.name = name
        self.definition = definition

    # ---- public entry points ------------------------------------------------

    def run_native(self, invocation: AgentInvocation) -> AgentInvocation:
        """Run a native-style agent inside the worktree.

        Claude is special-cased into headless print mode so orchestration
        remains non-interactive. Other native CLIs keep the existing
        interactive/PTy behavior.
        """
        assert_command_available(self.definition)
        invocation.cwd.mkdir(parents=True, exist_ok=True)
        prompt_file = invocation.cwd / "ERGON_PROMPT.md"
        prompt_file.write_text(invocation.prompt, encoding="utf-8")

        invocation.log_path.parent.mkdir(parents=True, exist_ok=True)
        if _is_claude_cli(self.definition.command, self.name):
            return self._run_claude_headless(invocation)

        cmd = _native_command(self.definition)
        env = build_subprocess_env(self.definition)

        script_bin = _which("script")
        if script_bin:
            wrapped = [
                script_bin,
                "-q",
                "-c",
                _join(cmd),
                str(invocation.log_path),
            ]
            invocation.started_at = datetime.now()
            proc = subprocess.run(wrapped, cwd=str(invocation.cwd), env=env)
            invocation.finished_at = datetime.now()
            invocation.exit_code = proc.returncode
        else:
            invocation.started_at = datetime.now()
            with invocation.log_path.open("w", encoding="utf-8") as logf:
                logf.write(f"# Native run of {self.name} — script(1) unavailable.\n")
                logf.write("# Stdout/stderr are inherited; no transcript captured.\n")
            proc = subprocess.run(cmd, cwd=str(invocation.cwd), env=env)
            invocation.finished_at = datetime.now()
            invocation.exit_code = proc.returncode

        invocation.output = _safe_read(invocation.log_path)
        return invocation

    def _run_claude_headless(self, invocation: AgentInvocation) -> AgentInvocation:
        """Run Claude Code in one-shot non-interactive mode."""
        env = build_subprocess_env(self.definition)
        prompt = _build_claude_prompt(invocation)

        base_cmd = _claude_print_command(self.definition, prompt)
        preferred_cmd = [*base_cmd, "--permission-mode", "acceptEdits"]

        invocation.started_at = datetime.now()
        try:
            proc = subprocess.run(
                preferred_cmd,
                cwd=str(invocation.cwd),
                env=env,
                capture_output=True,
                text=True,
                timeout=1800,
            )
            permission_mode_used = True
            if _unknown_flag(proc, "--permission-mode"):
                proc = subprocess.run(
                    base_cmd,
                    cwd=str(invocation.cwd),
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=1800,
                )
                permission_mode_used = False
        except FileNotFoundError as e:
            raise AgentNotAvailable(str(e)) from e
        invocation.finished_at = datetime.now()
        invocation.exit_code = proc.returncode

        body = _format_claude_log(
            command=self.definition.command,
            used_permission_mode=permission_mode_used,
            prompt=prompt,
            stdout=proc.stdout,
            stderr=proc.stderr,
            exit_code=proc.returncode,
        )
        invocation.output = body
        invocation.log_path.write_text(body, encoding="utf-8")
        return invocation

    def run_controlled(self, invocation: AgentInvocation) -> AgentInvocation:
        """Pipe the prompt to the CLI on stdin and capture its stdout."""
        assert_command_available(self.definition)
        invocation.log_path.parent.mkdir(parents=True, exist_ok=True)

        invocation_type = _invocation_type(self.definition)
        if invocation_type == "claude_print":
            return self._run_claude_print(invocation)

        cmd = _controlled_command(self.definition)
        env = build_subprocess_env(self.definition)

        invocation.started_at = datetime.now()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(invocation.cwd),
                input=invocation.prompt,
                capture_output=True,
                text=True,
                env=env,
                timeout=600,
            )
        except FileNotFoundError as e:
            raise AgentNotAvailable(str(e)) from e
        invocation.finished_at = datetime.now()
        invocation.exit_code = proc.returncode

        body = proc.stdout
        if proc.stderr.strip():
            body = body + "\n\n---\n[stderr]\n" + proc.stderr
        invocation.output = body
        invocation.log_path.write_text(body, encoding="utf-8")
        return invocation

    def _run_claude_print(self, invocation: AgentInvocation) -> AgentInvocation:
        """Run Claude in non-interactive print mode for controlled roles."""
        env = build_subprocess_env(self.definition)
        cmd = _claude_print_command(self.definition, invocation.prompt)

        invocation.started_at = datetime.now()
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(invocation.cwd),
                capture_output=True,
                text=True,
                env=env,
                timeout=1800,
            )
        except FileNotFoundError as e:
            raise AgentNotAvailable(str(e)) from e
        invocation.finished_at = datetime.now()
        invocation.exit_code = proc.returncode

        body = proc.stdout
        if proc.stderr.strip():
            body = body + "\n\n---\n[stderr]\n" + proc.stderr
        invocation.output = body
        invocation.log_path.write_text(body, encoding="utf-8")
        return invocation


def _which(name: str) -> str | None:
    return which(name)


def _join(cmd: list[str]) -> str:
    import shlex

    return " ".join(shlex.quote(c) for c in cmd)


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _is_claude_cli(command: str, agent_name: str) -> bool:
    return Path(command).name == "claude" or agent_name == "claude"


_DEFAULT_MODEL_FLAG: Final[tuple[str, ...]] = ("--model",)


def _invocation_type(definition: AgentDef) -> str:
    return definition.invocation or "stdin"


def _native_command(definition: AgentDef) -> list[str]:
    cmd = [definition.command]
    if definition.model:
        cmd.extend([*_DEFAULT_MODEL_FLAG, definition.model])
    cmd.extend(definition.args)
    return cmd


def _controlled_command(definition: AgentDef) -> list[str]:
    invocation_type = _invocation_type(definition)
    cmd = [definition.command]
    if invocation_type == "codex_exec":
        cmd.append("exec")
        if definition.model:
            cmd.extend(["-m", definition.model])
        cmd.extend(definition.args)
        return cmd
    if definition.model:
        cmd.extend([*_DEFAULT_MODEL_FLAG, definition.model])
    cmd.extend(definition.args)
    return cmd


def _claude_print_command(definition: AgentDef, prompt: str) -> list[str]:
    cmd = [definition.command]
    if definition.model:
        cmd.extend(["--model", definition.model])
    cmd.extend(definition.args)
    cmd.extend(["-p", prompt])
    return cmd


def _build_claude_prompt(invocation: AgentInvocation) -> str:
    task = _safe_read(invocation.cwd / "ERGON_TASK.md")
    context = _safe_read(invocation.cwd / "ERGON_CONTEXT.md")
    constraints = _safe_read(invocation.cwd / "ERGON_CONSTRAINTS.md")
    sections = [
        "Implement the task described below.",
        "Follow all constraints.",
        "Make changes directly to the repository in the current working directory.",
        "When finished, exit after printing a concise summary of what you changed and what you validated.",
    ]
    if task:
        sections.extend(["", "TASK:", task])
    if context:
        sections.extend(["", "CONTEXT:", context])
    if constraints:
        sections.extend(["", "CONSTRAINTS:", constraints])
    if invocation.prompt:
        sections.extend(["", "ADDITIONAL ERGON INSTRUCTIONS:", invocation.prompt])
    return "\n".join(sections).strip() + "\n"


def _unknown_flag(proc: subprocess.CompletedProcess[str], flag: str) -> bool:
    combined = "\n".join(part for part in (proc.stdout, proc.stderr) if part).lower()
    flag_text = flag.lower()
    return (
        flag_text in combined
        and any(token in combined for token in ("unknown", "unrecognized", "unexpected"))
    )


def _format_claude_log(
    command: str,
    used_permission_mode: bool,
    prompt: str,
    stdout: str,
    stderr: str,
    exit_code: int,
) -> str:
    parts = [
        "# Claude headless run",
        "",
        f"$ {command} -p <prompt>"
        + (" --permission-mode acceptEdits" if used_permission_mode else ""),
        "",
        "[prompt]",
        prompt,
        "",
        "[stdout]",
        stdout or "",
    ]
    if stderr.strip():
        parts.extend(["", "[stderr]", stderr])
    parts.extend(["", f"[exit {exit_code}]", ""])
    return "\n".join(parts)
