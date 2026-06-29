import subprocess
import sys
import shutil

def run_doctor(live=False):
    print("[*] Mighty Mouse Doctor")
    print("[*] Checking system readiness...")
    
    # 1. Base Package checks
    has_errors = False
    
    # Check Python version
    if sys.version_info < (3, 10):
        print("[-] Python version must be >= 3.10")
        has_errors = True
    else:
        print("[+] Python version is >= 3.10")
        
    # Check pyyaml
    try:
        import yaml
        print("[+] PyYAML is installed")
    except ImportError:
        print("[-] PyYAML is missing")
        has_errors = True

    # 2. Process Audit (No shell=True)
    try:
        res = subprocess.run(["ps", "aux"], capture_output=True, text=True)
        if "mighty_mouse_agent.py" in res.stdout:
            print("[!] Found potentially stale mighty_mouse_agent processes")
    except Exception as e:
        print(f"[-] Could not check processes: {e}")

    # 3. Live mode (Ollama) checks
    if live:
        print("[*] Checking Ollama health for --live mode...")
        ollama_path = shutil.which("ollama")
        if not ollama_path:
            print("[-] Ollama is not installed or not in PATH")
            has_errors = True
        else:
            print("[+] Ollama is in PATH")
            try:
                res = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=5)
                if res.returncode == 0:
                    print("[+] Ollama service is responsive")
                else:
                    print("[-] Ollama service returned an error")
                    has_errors = True
            except subprocess.TimeoutExpired:
                print("[-] Ollama service timed out")
                has_errors = True
            except Exception as e:
                print(f"[-] Ollama service error: {e}")
                has_errors = True
                
    if has_errors:
        print("\n[-] Doctor found issues.")
        sys.exit(1)
    else:
        print("\n[+] Doctor checks passed.")
        sys.exit(0)
