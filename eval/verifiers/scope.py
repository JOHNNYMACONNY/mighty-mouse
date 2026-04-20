import os
import subprocess

def verify(expected_files):
    # Use git status to find modified files
    res = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
    modified = []
    for line in res.stdout.split('\n'):
        if line.strip():
            # Extract path, handle quoted paths
            path = line[3:].strip()
            if '"' in path: path = path.replace('"', '')
            modified.append(path)
            
    ignored_prefixes = ['.gsd/', 'src/orchestrator/', 'eval/', '.DS_Store', 'logs/', 'autoresearch', 'baseline_run.log', 'configs/', 'scratch/']
    
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
        if os.path.basename(f_clean).startswith('._') or f_clean.endswith('.log') or f_clean.endswith('.tsv'):
            continue
            
        # Ignore directory paths if they are parents of any expected files
        is_parent = False
        for exp in expected_files:
            if exp.startswith(f_clean + '/') or exp == f_clean:
                is_parent = True
                break
        if is_parent:
            continue
        
        unexpected.append(f)

    missing = [f for f in expected_files if f not in modified and not os.path.exists(f)]
    passed = (len(unexpected) == 0 and len(missing) == 0)
    msg = "Scope verified." if passed else f"Scope fail. Unexp: {unexpected} Miss: {missing}"
    return passed, msg
