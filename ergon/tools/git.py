from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


class GitError(RuntimeError):
    pass


@dataclass
class GitResult:
    stdout: str
    stderr: str
    returncode: int


def run_git(args: list[str], cwd: Path, check: bool = True) -> GitResult:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
    )
    if check and proc.returncode != 0:
        raise GitError(
            f"git {' '.join(args)} failed (cwd={cwd}): {proc.stderr.strip()}"
        )
    return GitResult(stdout=proc.stdout, stderr=proc.stderr, returncode=proc.returncode)


def status_short(cwd: Path) -> str:
    return run_git(["status", "--short"], cwd).stdout


def diff_against(base_branch: str, cwd: Path) -> str:
    """Return a unified diff of HEAD against base_branch (3-dot)."""
    res = run_git(["diff", f"{base_branch}..."], cwd, check=False)
    if res.returncode != 0:
        # Fallback: maybe base_branch isn't reachable; diff against working tree only.
        res = run_git(["diff"], cwd, check=False)
    return res.stdout


def changed_files(base_branch: str, cwd: Path) -> list[str]:
    res = run_git(
        ["diff", "--name-only", f"{base_branch}..."], cwd, check=False
    )
    if res.returncode != 0:
        res = run_git(["diff", "--name-only"], cwd, check=False)
    return [line.strip() for line in res.stdout.splitlines() if line.strip()]


def current_branch(cwd: Path) -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()


def has_branch(name: str, cwd: Path) -> bool:
    res = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{name}"],
        cwd,
        check=False,
    )
    return res.returncode == 0
