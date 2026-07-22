import json
import os
from unittest.mock import MagicMock, patch
from src.mighty_mouse.orchestrator.mighty_mouse_agent import solve

def test_stage_planner_mode(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("model: gemma4:e4b\nprovider: mock\n")

    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({"id": "task_stage_1", "task": "Add a feature"}))

    plan_output_file = tmp_path / "custom_plan.md"

    mock_client = MagicMock()
    mock_client.generate_content.return_value = "<plan>\n1. Audit\n2. Scope\n3. Implementation steps\n</plan>"
    mock_client.last_metadata = {"usage": {"total_tokens": 100}}

    with patch("src.mighty_mouse.orchestrator.mighty_mouse_agent.GeminiClient", return_value=mock_client):
        solve(
            str(config_file),
            str(task_file),
            stage="planner",
            plan_file=str(plan_output_file)
        )

        assert plan_output_file.exists()
        assert "<plan>" in plan_output_file.read_text()

def test_stage_coder_mode_consumes_plan(tmp_path):
    config_file = tmp_path / "config.yaml"
    config_file.write_text("model: gemma4:e4b\nprovider: mock\n")

    task_file = tmp_path / "task.json"
    task_file.write_text(json.dumps({"id": "task_stage_2", "task": "Execute plan"}))

    plan_file = tmp_path / "stage1_plan.md"
    plan_file.write_text("<plan>Refactor function X in main.py</plan>")

    mock_client = MagicMock()
    mock_client.generate_content.return_value = "```python:main.py\ndef main(): pass\n```"
    mock_client.last_metadata = {"usage": {"total_tokens": 120}}

    with patch("src.mighty_mouse.orchestrator.mighty_mouse_agent.GeminiClient", return_value=mock_client):
        solve(
            str(config_file),
            str(task_file),
            workspace=str(tmp_path),
            stage="coder",
            plan_file=str(plan_file)
        )

        # Verify that prompt sent to client contained the stage 1 blueprint
        args, _ = mock_client.generate_content.call_args
        user_prompt = args[1]
        assert "<stage1_blueprint>" in user_prompt
        assert "<plan>Refactor function X in main.py</plan>" in user_prompt
        assert (tmp_path / "main.py").exists()
