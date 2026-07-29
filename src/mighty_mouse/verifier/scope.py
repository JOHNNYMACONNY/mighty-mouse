"""Git-based change-scope and task fixture verification."""

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


def verify_task_scope(task_config: dict, workspace: str | None = None) -> tuple[bool, str, dict]:
    """Verify scope for task configurations, tracking expected files and ghost files."""
    expected_files = task_config.get('expected_files', [])
    fixture_dir = task_config.get('fixture_dir')

    target_dir = os.path.abspath(workspace) if workspace else os.getcwd()
    in_workspace = 'workspaces/' in target_dir

    found_files = []
    if in_workspace:
        for root, dirs, files in os.walk(target_dir):
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'logs']]
            for f in files:
                rel_path = os.path.relpath(os.path.join(root, f), target_dir)
                if rel_path.startswith('./'):
                    rel_path = rel_path[2:]
                found_files.append(rel_path)
    else:
        res = subprocess.run(['git', '-C', target_dir, 'ls-files', '--modified', '--others', '--exclude-standard'], capture_output=True, text=True)
        if res.returncode == 0:
            found_files = [f for f in res.stdout.splitlines() if os.path.exists(os.path.join(target_dir, f))]

    fixture_paths = set()
    if fixture_dir:
        repo_root = os.path.abspath(os.path.join(target_dir, "../..")) if in_workspace else target_dir
        fixture_abs = os.path.join(repo_root, fixture_dir)
        if os.path.exists(fixture_abs):
            for root, _, files in os.walk(fixture_abs):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), fixture_abs)
                    fixture_paths.add(rel)

    universal = {'.gitignore', 'CHECKLIST.md', 'test_script.py', 'test_runner.py', 'requirements.txt', 'START-HERE-ANTIGRAVITY.md'}

    ignored_prefixes = [
        '.gsd/', 'src/mighty_mouse/orchestrator/', 'eval/', '.DS_Store', 'logs/', 'autoresearch',
        'baseline_run.log', 'configs/', 'scratch/', 'workspaces/', '.git/', 'src/',
        '.venv/', '__pycache__/', '.mighty/'
    ]

    ghost_files_flagged = []
    fixture_files_preserved = 0
    harness_files_ignored = 0

    for f in found_files:
        f_clean = f.rstrip('/')

        if f_clean in expected_files:
            continue

        if f_clean in fixture_paths:
            fixture_files_preserved += 1
            continue

        if f_clean in universal:
            harness_files_ignored += 1
            continue

        if any(f_clean.startswith(p) for p in ignored_prefixes):
            harness_files_ignored += 1
            continue

        if os.path.basename(f_clean).startswith('._') or f_clean.endswith('.log') or f_clean.endswith('.tsv') or f_clean.endswith('.json') or f_clean.endswith('.md'):
            harness_files_ignored += 1
            continue

        ghost_files_flagged.append(f)

    missing = [f for f in expected_files if f not in found_files and not os.path.exists(os.path.join(target_dir, f))]

    passed = (len(ghost_files_flagged) == 0 and len(missing) == 0)

    signal = {
        "ghost_files_flagged_post_run": ghost_files_flagged,
        "fixture_files_preserved": fixture_files_preserved,
        "harness_files_ignored": harness_files_ignored,
        "scope_status": "PASS" if passed else "FAIL"
    }

    msg = "Scope verified." if passed else f"Scope fail. Unexp: {ghost_files_flagged} Miss: {missing}"
    return passed, msg, signal
