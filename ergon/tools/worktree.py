from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ergon.tools.git import GitError, has_branch, run_git
from ergon.utils.paths import worktrees_root


@dataclass
class Worktree:
    repo_root: Path
    path: Path
    branch: str
    base_branch: str


def worktree_path_for(repo_name: str, task_id: str, slug: str, agent: str) -> Path:
    return worktrees_root() / repo_name / f"{task_id}-{slug}-{agent}"


def branch_name_for(task_id: str, slug: str, agent: str) -> str:
    return f"ergon/{task_id}-{slug}/{agent}"


def create_worktree(
    repo_root: Path,
    repo_name: str,
    task_id: str,
    slug: str,
    agent: str,
    base_branch: str,
) -> Worktree:
    path = worktree_path_for(repo_name, task_id, slug, agent)
    branch = branch_name_for(task_id, slug, agent)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        # Already created — return descriptor without re-creating.
        return Worktree(
            repo_root=repo_root, path=path, branch=branch, base_branch=base_branch
        )

    if has_branch(branch, repo_root):
        # Reuse the branch if it already exists.
        run_git(["worktree", "add", str(path), branch], repo_root)
    else:
        run_git(
            ["worktree", "add", str(path), "-b", branch, base_branch],
            repo_root,
        )
    return Worktree(repo_root=repo_root, path=path, branch=branch, base_branch=base_branch)


def remove_worktree(repo_root: Path, path: Path, force: bool = False) -> None:
    args = ["worktree", "remove"]
    if force:
        args.append("--force")
    args.append(str(path))
    try:
        run_git(args, repo_root)
    except GitError:
        # As a last resort, fall back to filesystem removal + prune.
        shutil.rmtree(path, ignore_errors=True)
        run_git(["worktree", "prune"], repo_root, check=False)


def list_worktrees(repo_root: Path) -> str:
    return run_git(["worktree", "list"], repo_root).stdout
