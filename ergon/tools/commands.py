from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CommandResult:
    command: str
    cwd: Path
    exit_code: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.exit_code == 0


def run_shell(
    command: str,
    cwd: Path,
    timeout: int | None = None,
    env: dict[str, str] | None = None,
) -> CommandResult:
    """Run a shell command and capture its output."""
    full_env = os.environ.copy()
    if env:
        full_env.update(env)
    try:
        proc = subprocess.run(
            command,
            cwd=str(cwd),
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=full_env,
        )
    except subprocess.TimeoutExpired as e:
        return CommandResult(
            command=command,
            cwd=cwd,
            exit_code=124,
            stdout=(e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, (bytes, bytearray)) else (e.stdout or ""),
            stderr=f"Timed out after {timeout}s",
        )
    return CommandResult(
        command=command,
        cwd=cwd,
        exit_code=proc.returncode,
        stdout=proc.stdout,
        stderr=proc.stderr,
    )
