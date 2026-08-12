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


def isolated_engine_paths(tmp_path, **overrides):
    segments_dir = tmp_path / "segments"
    segments_dir.mkdir()
    agent_config = tmp_path / "agent.yaml"
    agent_config.write_text("model: gemma\n")
    paths = {
        "results_path": str(tmp_path / "benchmark_results.json"),
        "mutation_log_path": str(tmp_path / "mutation_log.jsonl"),
        "segments_dir": str(segments_dir),
        "agent_config": str(agent_config),
    }
    paths.update(overrides)

    root = os.path.realpath(str(tmp_path))
    for key in (
        "results_path",
        "mutation_log_path",
        "segments_dir",
        "agent_config",
    ):
        path = paths[key]
        assert os.path.commonpath((root, os.path.realpath(path))) == root
    return paths
