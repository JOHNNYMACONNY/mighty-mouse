import os

def verify(expected_files):
    import subprocess
    modified = []
    res = subprocess.run(['git', 'ls-files', '--modified', '--others', '--exclude-standard'], capture_output=True, text=True)
    if res.returncode == 0:
        modified = res.stdout.splitlines()
            
    ignored_prefixes = ['.gsd/', 'src/orchestrator/', 'eval/', '.DS_Store', 'logs/', 'autoresearch', 'baseline_run.log', 'configs/', 'scratch/', 'workspaces/', '.git/', 'src/', '.venv/', '__pycache__/']
    
    unexpected = []
    for f in modified:
        f_clean = f.rstrip('/')
        # Ignore if it's explicitly expected or a known system file
        if f_clean in expected_files or f_clean in ('.gitignore', 'CHECKLIST.md', 'test_script.py', 'test_runner.py', 'requirements.txt', 'val_sys.py', 'helpers.py', 'legacy_registry.py', 'START-HERE-ANTIGRAVITY.md'):
            continue
        # Ignore if it's in an ignored prefix
        if any(f_clean.startswith(p) for p in ignored_prefixes):
            continue
        # Ignore AppleDouble or specific extensions/docs
        if os.path.basename(f_clean).startswith('._') or f_clean.endswith('.log') or f_clean.endswith('.tsv') or f_clean.endswith('.json') or f_clean.endswith('.md'):
            continue
            
        unexpected.append(f)

    missing = [f for f in expected_files if f not in modified and not os.path.exists(f)]
    passed = (len(unexpected) == 0 and len(missing) == 0)
    msg = "Scope verified." if passed else f"Scope fail. Unexp: {unexpected} Miss: {missing}"
    return passed, msg
