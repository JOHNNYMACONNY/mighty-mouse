import json
import os
from unittest.mock import MagicMock, patch
from eval.compute_scaler import invoke_with_scaling

def test_best_of_n_ranker_selects_minimal_diff(tmp_path):
    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({"id": "task_rank_123"}))

    diff_outputs = ["30\t20\tfile1.py\n", "3\t2\tfile1.py\n", "100\t50\tfile1.py\n"]
    call_count = {"idx": 0}

    def mock_subprocess_run(cmd, capture_output=False, text=False):
        proc = MagicMock()
        cmd_str = " ".join(cmd) if isinstance(cmd, list) else str(cmd)
        
        if "git" in cmd_str and "diff" in cmd_str:
            idx = call_count["idx"] % len(diff_outputs)
            proc.stdout = diff_outputs[idx]
            call_count["idx"] += 1
        elif "run_benchmark.py" in cmd_str:
            os.makedirs("logs", exist_ok=True)
            with open("logs/benchmark_results.json", "w") as f:
                json.dump({"results": [{"task_id": "task_rank_123", "status": "success"}]}, f)
        return proc

    with patch("eval.compute_scaler.run_command", return_value=(0, "Success", "")):
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            ret, out, err = invoke_with_scaling("python agent.py cfg.yaml task.json", str(task_file), variations=3)
            assert ret == 0
            assert out == "Success"
