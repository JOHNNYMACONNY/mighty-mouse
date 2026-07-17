import os

def verify(task_config):
    expected_files = task_config.get('expected_files', [])
    fixture_dir = task_config.get('fixture_dir')
    
    # Detect if we are in an isolated workspace (inside workspaces/ dir)
    cwd = os.getcwd()
    in_workspace = 'workspaces/' in cwd
    
    found_files = []
    if in_workspace:
        # In isolated workspace: just list all files in CWD
        for root, dirs, files in os.walk('.'):
            # Exclude ignored dirs
            dirs[:] = [d for d in dirs if d not in ['.git', '__pycache__', 'logs']]
            for f in files:
                rel_path = os.path.relpath(os.path.join(root, f), '.')
                if rel_path.startswith('./'): rel_path = rel_path[2:]
                found_files.append(rel_path)
    else:
        # In root: use git ls-files
        import subprocess
        res = subprocess.run(['git', 'ls-files', '--modified', '--others', '--exclude-standard'], capture_output=True, text=True)
        if res.returncode == 0:
            found_files = [f for f in res.stdout.splitlines() if os.path.exists(f)]
            
    # Resolve fixtures
    fixture_paths = set()
    if fixture_dir:
        # Resolve fixtures relative to repo root (assumed to be ../.. from workspace)
        repo_root = os.path.abspath(os.path.join(cwd, "../..")) if in_workspace else os.path.abspath(cwd)
        fixture_abs = os.path.join(repo_root, fixture_dir)
        if os.path.exists(fixture_abs):
            for root, _, files in os.walk(fixture_abs):
                for f in files:
                    rel = os.path.relpath(os.path.join(root, f), fixture_abs)
                    fixture_paths.add(rel)

    # Universal metadata (non-code artifacts)
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
        
        # 1. Ignore if explicitly expected
        if f_clean in expected_files:
            continue
            
        # 2. Check if it is a declared fixture
        if f_clean in fixture_paths:
            fixture_files_preserved += 1
            continue
            
        # 3. Check if universal metadata
        if f_clean in universal:
            harness_files_ignored += 1
            continue
            
        # 4. Ignore if it's in an ignored prefix (includes .mighty/)
        if any(f_clean.startswith(p) for p in ignored_prefixes):
            harness_files_ignored += 1
            continue
            
        # 5. Ignore AppleDouble or specific extensions/docs
        if os.path.basename(f_clean).startswith('._') or f_clean.endswith('.log') or f_clean.endswith('.tsv') or f_clean.endswith('.json') or f_clean.endswith('.md'):
            harness_files_ignored += 1
            continue
            
        # Anything else is an unexpected ghost
        ghost_files_flagged.append(f)

    # Missing check
    missing = [f for f in expected_files if f not in found_files and not os.path.exists(f)]
    
    passed = (len(ghost_files_flagged) == 0 and len(missing) == 0)
    
    telemetry = {
        "ghost_files_flagged_post_run": ghost_files_flagged,
        "fixture_files_preserved": fixture_files_preserved,
        "harness_files_ignored": harness_files_ignored,
        "scope_status": "PASS" if passed else "FAIL"
    }
    
    msg = "Scope verified." if passed else f"Scope fail. Unexp: {ghost_files_flagged} Miss: {missing}"
    return passed, msg, telemetry
