"""Git-based change-scope verification."""

from __future__ import annotations

import fnmatch
import os
import subprocess


def _git_paths(workspace: str) -> tuple[list[str], str | None]:
    inside = subprocess.run(
        ["git", "-C", workspace, "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
    )
    if inside.returncode != 0 or inside.stdout.strip() != "true":
        return [], "Scope checking requires a Git worktree."

    changed = subprocess.run(
        ["git", "-C", workspace, "diff", "--name-only", "--diff-filter=ACMR", "HEAD", "--"],
        capture_output=True,
        text=True,
    )
    untracked = subprocess.run(
        ["git", "-C", workspace, "ls-files", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
    )
    if changed.returncode != 0 or untracked.returncode != 0:
        detail = (changed.stderr + untracked.stderr).strip()
        return [], detail or "Unable to inspect Git changes."
    paths = sorted(set(changed.stdout.splitlines()) | set(untracked.stdout.splitlines()))
    return paths, None


def _is_allowed(path: str, allowed_paths: list[str]) -> bool:
    normalized = path.replace(os.sep, "/").lstrip("./")
    for rule in allowed_paths:
        candidate = rule.replace(os.sep, "/").lstrip("./").rstrip("/")
        if not candidate:
            continue
        if normalized == candidate or normalized.startswith(candidate + "/"):
            return True
        if any(char in candidate for char in "*?[") and fnmatch.fnmatch(normalized, candidate):
            return True
    return False


def check_scope(workspace: str, allowed_paths: list[str]) -> tuple[bool, str, list[str]]:
    changed_paths, error = _git_paths(workspace)
    if error:
        return False, error, []
    violations = [path for path in changed_paths if not _is_allowed(path, allowed_paths)]
    if violations:
        return False, "Out-of-scope changes: " + ", ".join(violations), violations
    return True, f"All {len(changed_paths)} changed path(s) are within scope.", []
