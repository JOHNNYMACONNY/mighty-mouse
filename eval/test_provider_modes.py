import importlib.util
import json
import os
import sys
import tempfile

from test_utils import ROOT, load_module as _load_module


def test_sim_requires_explicit_opt_in():
    client_mod = _load_module("gemini_client", "src/mighty_mouse/orchestrator/gemini_client.py")
    try:
        client_mod.GeminiClient({"provider": "sim"})
        raise AssertionError("Simulation should require allow_simulation=true")
    except ValueError as e:
        assert "allow_simulation=true" in str(e)


def test_benchmark_guard_rejects_sim_config():
    run_parallel = _load_module("benchmark_service", "src/mighty_mouse/services/benchmark_service.py")
    try:
        run_parallel._assert_live_benchmark_config({"provider": "sim", "allow_simulation": True})
        raise AssertionError("Benchmark guard should reject simulation config")
    except RuntimeError as e:
        assert "live provider" in str(e)


def test_agent_writes_run_metadata_for_sim_dev_mode():
    agent = _load_module("mighty_mouse_agent", "src/mighty_mouse/orchestrator/mighty_mouse_agent.py")
    cfg_path = os.path.join(ROOT, "configs/mighty_mouse_dev_sim.yaml")
    task_path = os.path.join(ROOT, "tasks/benchmark/task_001_legacy_registry_ratelimiter.json")

    with tempfile.TemporaryDirectory() as tmp:
        agent.solve(cfg_path, task_path, workspace=tmp)
        metadata_path = os.path.join(tmp, "logs", "last_agent_run.json")
        checklist_path = os.path.join(tmp, "CHECKLIST.md")

        assert os.path.exists(metadata_path), "Run metadata was not written"
        assert os.path.exists(checklist_path), "Checklist was not written"

        with open(metadata_path, "r") as f:
            metadata = json.load(f)

        assert metadata["provider"] == "sim"
        assert metadata["mode"] == "simulation"
        assert metadata["workspace"] == tmp
        assert "output_files" in metadata
        assert "written_files" in metadata
        assert "deleted_files" in metadata


if __name__ == "__main__":
    test_sim_requires_explicit_opt_in()
    print("PASS: sim provider requires explicit opt-in")
    test_benchmark_guard_rejects_sim_config()
    print("PASS: benchmark guard rejects simulation config")
    test_agent_writes_run_metadata_for_sim_dev_mode()
    print("PASS: agent writes metadata in dev sim mode")
