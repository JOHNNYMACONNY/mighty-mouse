import os

def verify(expected_files):
    # Parallel-Safe: Use os.walk instead of git status to find local changes
    modified = []
    for root, dirs, files in os.walk('.'):
        for f in files:
            rel_path = os.path.relpath(os.path.join(root, f), '.')
            if rel_path.startswith('./'): rel_path = rel_path[2:]
            modified.append(rel_path)
            
    ignored_prefixes = ['.gsd/', 'src/orchestrator/', 'eval/', '.DS_Store', 'logs/', 'autoresearch', 'baseline_run.log', 'configs/', 'scratch/', 'workspaces/']
    
    unexpected = []
    for f in modified:
        f_clean = f.rstrip('/')
        # Ignore if it's explicitly expected or a known system file
        if f_clean in expected_files or f_clean == 'CHECKLIST.md' or f_clean == 'test_runner.py':
            continue
        # Ignore if it's in an ignored prefix
        if any(f_clean.startswith(p) for p in ignored_prefixes):
            continue
        # Ignore AppleDouble or specific extensions
        if os.path.basename(f_clean).startswith('._') or f_clean.endswith('.log') or f_clean.endswith('.tsv') or f_clean.endswith('.json'):
            continue
            
        unexpected.append(f)

    missing = [f for f in expected_files if f not in modified and not os.path.exists(f)]
    passed = (len(unexpected) == 0 and len(missing) == 0)
    msg = "Scope verified." if passed else f"Scope fail. Unexp: {unexpected} Miss: {missing}"
    return passed, msg
