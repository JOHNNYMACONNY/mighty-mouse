import importlib.util
import os

# ROOT is the project root (parent of eval/)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Ensure we can load from src/mighty_mouse/orchestrator and ROOT
if os.path.join(ROOT, "src", "mighty_mouse", "orchestrator") not in os.sys.path:
    os.sys.path.insert(0, os.path.join(ROOT, "src", "mighty_mouse", "orchestrator"))
if ROOT not in os.sys.path:
    os.sys.path.insert(0, ROOT)

def load_module(name, rel_path):
    """
    Loads a module from a relative path from the project ROOT.
    """
    path = os.path.join(ROOT, rel_path)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
