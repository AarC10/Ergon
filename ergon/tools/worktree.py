from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from ergon.tools.git import GitError, has_branch, run_git
from ergon.utils.paths import worktrees_root
from ergon.utils.slug import slugify_identifier


@dataclass
class Worktree:
    repo_root: Path
    path: Path
    branch: str
    base_branch: str


def _sanitize_components(
    repo_name: str, task_id: str, slug: str, agent: str
) -> tuple[str, str, str, str]:
    """Reduce identifiers to slug-safe forms suitable for paths and git refs."""
    safe_repo = slugify_identifier(repo_name)
    safe_agent = slugify_identifier(agent)
    safe_slug = slugify_identifier(slug)
    safe_id = slugify_identifier(task_id)
    if not (safe_repo and safe_agent and safe_slug and safe_id):
        raise ValueError(
            "repo / agent / slug / task_id must each contain at least one "
            "slug-safe character (letters, digits, dashes, underscores)."
        )
    return safe_repo, safe_id, safe_slug, safe_agent


def worktree_path_for(repo_name: str, task_id: str, slug: str, agent: str) -> Path:
    safe_repo, safe_id, safe_slug, safe_agent = _sanitize_components(
        repo_name, task_id, slug, agent
    )
    return worktrees_root() / safe_repo / f"{safe_id}-{safe_slug}-{safe_agent}"


def branch_name_for(task_id: str, slug: str, agent: str) -> str:
    # repo_name is irrelevant to the branch — use a placeholder so the
    # _sanitize_components contract still holds.
    _, safe_id, safe_slug, safe_agent = _sanitize_components(
        "ergon", task_id, slug, agent
    )
    return f"ergon/{safe_id}-{safe_slug}/{safe_agent}"


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
        shutil.rmtree(path, ignore_errors=True)
        run_git(["worktree", "prune"], repo_root, check=False)


def list_worktrees(repo_root: Path) -> str:
    return run_git(["worktree", "list"], repo_root).stdout
