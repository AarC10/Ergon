from __future__ import annotations

import os
import subprocess
from datetime import datetime
from pathlib import Path

from ergon.agents.base import AgentInvocation, AgentNotAvailable, assert_command_available
from ergon.core.config import AgentDef


class CliAgent:
    """Generic adapter that fronts an AI CLI binary (claude, codex, gemini, ...)."""

    def __init__(self, name: str, definition: AgentDef):
        self.name = name
        self.definition = definition

    # ---- public entry points ------------------------------------------------

    def run_native(self, invocation: AgentInvocation) -> AgentInvocation:
        """Hand control to the underlying CLI inside the worktree.

        The agent's prompt is dropped into ERGON_PROMPT.md inside the cwd so
        the user (or the CLI itself, if so configured) can read it. Stdin/
        stdout/stderr are inherited so the user can drive the CLI normally.
        Whatever the CLI prints is also tee'd into the task log via the
        wrapping shell `script` command if available; otherwise we rely on
        the CLI's own transcript and capture stdout via tee.
        """
        assert_command_available(self.definition)
        invocation.cwd.mkdir(parents=True, exist_ok=True)
        prompt_file = invocation.cwd / "ERGON_PROMPT.md"
        prompt_file.write_text(invocation.prompt, encoding="utf-8")

        invocation.log_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [self.definition.command, *self.definition.args]
        env = os.environ.copy()
        env.update(self.definition.env)

        # Best-effort log capture without blocking interactivity: run under
        # `script` when available so the full PTY transcript lands on disk.
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

    def run_controlled(self, invocation: AgentInvocation) -> AgentInvocation:
        """Pipe the prompt to the CLI on stdin and capture its stdout.

        This assumes the underlying CLI accepts a one-shot prompt on stdin
        (which Claude CLI, codex, and gemini all support in some form).
        Adapters can later override this with subcommand flags.
        """
        assert_command_available(self.definition)
        invocation.log_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = [self.definition.command, *self.definition.args]
        env = os.environ.copy()
        env.update(self.definition.env)

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


def _which(name: str) -> str | None:
    import shutil as _sh

    return _sh.which(name)


def _join(cmd: list[str]) -> str:
    import shlex

    return " ".join(shlex.quote(c) for c in cmd)


def _safe_read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
