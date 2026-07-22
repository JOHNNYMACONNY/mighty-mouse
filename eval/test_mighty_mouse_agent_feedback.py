import os
import json
import pytest
from unittest.mock import patch, MagicMock
from src.mighty_mouse.orchestrator.mighty_mouse_agent import _solve_inner

def test_solve_inner_temperature_and_feedback():
    p_cfg_path = "configs/gemma.json"
    task_input = "tasks/mock_task.json"

    if not os.path.exists("configs"):
        os.makedirs("configs", exist_ok=True)
    if not os.path.exists("tasks"):
        os.makedirs("tasks", exist_ok=True)

    with open(p_cfg_path, "w") as f:
        json.dump({"provider": "sim", "allow_simulation": True, "prompt_segments": []}, f)
    with open(task_input, "w") as f:
        json.dump({"id": "mock_task_01", "task": "Mock task"}, f)

    with patch("src.mighty_mouse.orchestrator.mighty_mouse_agent.GeminiClient") as MockClient:
        mock_instance = MagicMock()
        mock_instance.generate_content.return_value = "```python:hello.py\nprint('hello')\n```"
        mock_instance.last_metadata = {}
        MockClient.return_value = mock_instance

        _solve_inner(p_cfg_path, task_input, feedback_str="Previous Pytest failed", temperature=0.45)

        # Assert GeminiClient was instantiated with temperature=0.45
        MockClient.assert_called_once()
        config_passed = MockClient.call_args[1]["config"]
        assert config_passed.get("temperature") == 0.45

        # Assert generate_content received structured XML feedback and disallowed patterns
        args = mock_instance.generate_content.call_args[0]
        user_prompt = args[1]
        assert "<execution_feedback>" in user_prompt
        assert "Previous Pytest failed" in user_prompt
        assert "<disallowed_patterns>" in user_prompt
