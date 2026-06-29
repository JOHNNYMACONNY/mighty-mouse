import importlib.util
import json
import os
import tempfile
from types import SimpleNamespace

from test_utils import ROOT, load_module as _load_module


def test_run_task_includes_round_logging():
    mod = _load_module("benchmark_service", "src/mighty_mouse/services/benchmark_service.py")
    original_cwd = os.getcwd()
    os.chdir(ROOT)
    original_subprocess_run = mod.subprocess.run
    original_rmtree = mod.shutil.rmtree
    original_load_config = mod._load_config

    def fake_run(cmd, capture_output=True, text=True, cwd=None, env=None, timeout=None):
        if str(cmd[1]).endswith("mighty_mouse_agent.py"):
            os.makedirs(os.path.join(cwd, "logs"), exist_ok=True)
            with open(os.path.join(cwd, "logs", "last_agent_run.json"), "w") as f:
                json.dump(
                    {
                        "provider": "gemini_api",
                        "model": "gemini-2.5-flash",
                        "mode": "live",
                        "written_files": ["main.py"],
                        "deleted_files": [],
                    },
                    f,
                    indent=2,
                )
            return SimpleNamespace(returncode=0, stdout="agent ok", stderr="")
        return SimpleNamespace(returncode=0, stdout="Task task_001_legacy_registry_ratelimiter success verified.", stderr="")

    try:
        mod.subprocess.run = fake_run
        mod.shutil.rmtree = lambda *args, **kwargs: None
        mod._load_config = lambda *args, **kwargs: {"provider": "gemini_api", "model": "gemini-2.5-flash", "allow_simulation": False}
        result = mod.run_task(os.path.join(ROOT, "tasks/benchmark/task_001_legacy_registry_ratelimiter.json"))
    finally:
        mod.subprocess.run = original_subprocess_run
        mod.shutil.rmtree = original_rmtree
        mod._load_config = original_load_config
        os.chdir(original_cwd)

    assert result["provider"] == "gemini_api"
    assert result["model"] == "gemini-2.5-flash"
    assert len(result["rounds"]) == 1
    assert result["rounds"][0]["run_metadata"]["written_files"] == ["main.py"]
    assert "verify_stdout" in result["rounds"][0]


if __name__ == "__main__":
    test_run_task_includes_round_logging()
    print("PASS: run_parallel logs provider/model and per-round metadata")
