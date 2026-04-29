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


class NotAGitRepo(RuntimeError):
    pass


def is_git_repo(path: Path) -> bool:
    """True if `path` is inside a git repo (works for linked worktrees too)."""
    res = run_git(["rev-parse", "--is-inside-work-tree"], path, check=False)
    return res.returncode == 0 and res.stdout.strip() == "true"


def git_dir(path: Path) -> Path:
    """Per-worktree git dir (e.g. /repo/.git or /repo/.git/worktrees/wt)."""
    res = run_git(["rev-parse", "--git-dir"], path, check=False)
    if res.returncode != 0:
        raise NotAGitRepo(f"{path} is not inside a git repository")
    raw = res.stdout.strip()
    p = Path(raw)
    if not p.is_absolute():
        p = (path / p).resolve()
    return p


def git_common_dir(path: Path) -> Path:
    """Shared git dir (always the main repo's .git, even from a linked worktree)."""
    res = run_git(["rev-parse", "--git-common-dir"], path, check=False)
    if res.returncode != 0:
        raise NotAGitRepo(f"{path} is not inside a git repository")
    raw = res.stdout.strip()
    p = Path(raw)
    if not p.is_absolute():
        p = (path / p).resolve()
    return p


def toplevel(path: Path) -> Path:
    """Working tree root for `path` (for linked worktrees, the worktree root)."""
    res = run_git(["rev-parse", "--show-toplevel"], path, check=False)
    if res.returncode != 0:
        raise NotAGitRepo(f"{path} is not inside a git repository")
    return Path(res.stdout.strip())


def common_toplevel(path: Path) -> Path | None:
    """The main repo's working tree root (best-effort).

    For a linked worktree, derives this from `git rev-parse --git-common-dir`'s
    parent. For the main worktree, equals `toplevel(path)`.
    """
    common = git_common_dir(path)
    # Common git dir is usually `<main_root>/.git`; parent is the main root.
    if common.name == ".git":
        return common.parent
    # Bare repo or unusual layout — fall back to current toplevel.
    try:
        return toplevel(path)
    except NotAGitRepo:
        return None


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
