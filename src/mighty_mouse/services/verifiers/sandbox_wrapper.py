import os
import sys
import resource
import socket
import builtins
import argparse
from pathlib import Path

# --- Security Configuration ---
MAX_CPU_TIME = 60  # Seconds
MAX_MEMORY_MB = 1024  # MB

# We allow READ access to the entire project root to load modules/libraries.
# We allow WRITE access ONLY to the current working directory (the task workspace).
PROJECT_ROOT = str(Path(__file__).parent.parent.resolve())
WORKSPACE_ROOT = os.getcwd()

class SecurityError(Exception):
    pass

def block_network():
    """Block network access by patching connection methods."""
    def guarded_connect(*args, **kwargs):
        print("[sandbox] BLOCKED: Network connection attempt.", file=sys.stderr)
        raise SecurityError("Network access is disabled in the sandbox.")
    
    socket.socket.connect = guarded_connect
    socket.socket.connect_ex = guarded_connect
    socket.getaddrinfo = guarded_connect
    socket.create_connection = guarded_connect

def block_filesystem():
    """Monkey-patch builtins.open to restrict file access."""
    original_open = builtins.open

    def guarded_open(file, mode='r', *args, **kwargs):
        try:
            target_path = Path(file).resolve()
            target_str = str(target_path)
            
            # Check for Write access
            is_write = any(m in mode for m in ('w', 'a', 'x', '+'))
            
            if is_write:
                if not target_str.startswith(WORKSPACE_ROOT):
                    print(f"[sandbox] BLOCKED: Write attempt outside workspace: {file}", file=sys.stderr)
                    raise SecurityError(f"Write access to path outside workspace is denied: {file}")
            else:
                # Read access: Allow workspace OR project root (for libs) OR standard python libs
                allowed_reads = [WORKSPACE_ROOT, PROJECT_ROOT, "/usr/lib", "/System/Library", sys.prefix]
                if not any(target_str.startswith(p) for p in allowed_reads):
                    print(f"[sandbox] BLOCKED: Read attempt outside allowed paths: {file}", file=sys.stderr)
                    raise SecurityError(f"Read access to path denied: {file}")
                    
        except SecurityError:
            raise
        except Exception:
            # If resolve fails, we'll let it pass for now as it might be a relative path that doesn't exist yet
            pass
        return original_open(file, mode, *args, **kwargs)

    builtins.open = guarded_open

def set_resource_limits():
    """Set CPU and Memory limits using the resource module."""
    # CPU Time Limit
    resource.setrlimit(resource.RLIMIT_CPU, (MAX_CPU_TIME, MAX_CPU_TIME))
    
    # Memory Limit (Address Space)
    memory_bytes = MAX_MEMORY_MB * 1024 * 1024
    try:
        resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))
    except (ValueError, resource.error):
        # Some OSs (like certain macOS versions) might restrict setting RLIMIT_AS for the current process
        print("[sandbox] WARNING: Could not set RLIMIT_AS (Memory Limit).", file=sys.stderr)

def run_sandbox(script_path, script_args):
    """Executes the target script within the sandboxed environment."""
    print(f"[sandbox] Initializing isolation for: {script_path}")
    
    # Apply Protections
    block_network()
    block_filesystem()
    set_resource_limits()

    # Prepare Environment
    sys.argv = [script_path] + script_args
    script_dir = os.path.dirname(os.path.abspath(script_path))
    if script_dir not in sys.path:
        sys.path.insert(0, script_dir)

    import runpy
    try:
        # Execute script
        runpy.run_path(script_path, run_name="__main__")
        
    except SystemExit as e:
        sys.exit(e.code)
    except SecurityError as e:
        print(f"[sandbox] SECURITY FAILURE: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"[sandbox] RUNTIME ERROR: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mighty Mouse Native Sandbox Wrapper")
    parser.add_argument("script", help="Path to the python script to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments to pass to the script")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.script):
        print(f"Error: Script not found: {args.script}")
        sys.exit(1)

    run_sandbox(args.script, args.args)
