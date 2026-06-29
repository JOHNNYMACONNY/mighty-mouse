import subprocess
import os

def run_task_tests(test_script):
    with open('test_runner.py', 'w') as f: f.write(test_script)
    try:
        res = subprocess.run(['python3', 'test_runner.py'], capture_output=True, text=True, timeout=10)
        passed = (res.returncode == 0)
        logs = res.stdout + res.stderr
    except Exception as e:
        passed = False
        logs = str(e)
    finally:
        if os.path.exists('test_runner.py'): os.remove('test_runner.py')
    return passed, logs
