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
    """Return a unified diff of the working tree against base_branch.

    Includes tracked modifications *and* untracked files (the latter via
    `git diff --no-index`), since AI agents typically edit/add files
    without committing.
    """
    tracked = run_git(["diff", base_branch], cwd, check=False).stdout
    parts: list[str] = [tracked]
    untracked = run_git(
        ["ls-files", "--others", "--exclude-standard"], cwd, check=False
    ).stdout.splitlines()
    for raw in untracked:
        f = raw.strip()
        if not f:
            continue
        proc = subprocess.run(
            ["git", "diff", "--no-index", "--", "/dev/null", f],
            cwd=str(cwd),
            capture_output=True,
            text=True,
        )
        # `--no-index` returns 1 when files differ — that's the normal case.
        if proc.returncode in (0, 1):
            parts.append(proc.stdout)
    return "".join(parts)


def changed_files(base_branch: str, cwd: Path) -> list[str]:
    tracked = run_git(
        ["diff", "--name-only", base_branch], cwd, check=False
    ).stdout.splitlines()
    untracked = run_git(
        ["ls-files", "--others", "--exclude-standard"], cwd, check=False
    ).stdout.splitlines()
    out: list[str] = []
    seen: set[str] = set()
    for line in [*tracked, *untracked]:
        f = line.strip()
        if f and f not in seen:
            seen.add(f)
            out.append(f)
    return out


def current_branch(cwd: Path) -> str:
    return run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd).stdout.strip()


def has_branch(name: str, cwd: Path) -> bool:
    res = run_git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{name}"],
        cwd,
        check=False,
    )
    return res.returncode == 0
