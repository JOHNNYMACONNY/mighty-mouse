import subprocess
import os

def check_scope(expected_files):
    result = subprocess.run(['git', 'status', '--porcelain'], capture_output=True, text=True)
    modified = []
    for line in result.stdout.splitlines():
        if line.strip():
            path = line[3:].strip()
            if '"' in path: path = path.replace('"', '')
            modified.append(path)
    ignored_prefixes = ['.gsd/', 'src/orchestrator/', 'eval/', '.DS_Store', 'logs/', 'autoresearch', 'baseline_run.log', 'configs/', 'scratch/']
    unexpected = [f for f in modified if f not in expected_files and f != 'CHECKLIST.md' and f != 'test_runner.py' and not any(f.startswith(p) for p in ignored_prefixes) and not os.path.basename(f).startswith('._') and not f.endswith('.log') and not f.endswith('.tsv')]
    missing = [f for f in expected_files if f not in modified and not os.path.exists(f)]
    passed = (len(unexpected) == 0 and len(missing) == 0)
    msg = "Scope verified." if passed else f"Scope fail. Unexp: {unexpected} Miss: {missing}"
    return passed, msg
