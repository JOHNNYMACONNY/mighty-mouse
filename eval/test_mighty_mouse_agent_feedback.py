import json
from unittest.mock import patch, MagicMock

from src.mighty_mouse.orchestrator.mighty_mouse_agent import _solve_inner


def test_solve_inner_temperature_and_feedback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    p_cfg_path = tmp_path / "gemma.json"
    task_input = tmp_path / "mock_task.json"
    workspace = tmp_path / "workspace"

    p_cfg_path.write_text(json.dumps({
        "provider": "sim",
        "allow_simulation": True,
        "prompt_segments": [],
    }))
    task_input.write_text(
        json.dumps({"id": "mock_task_01", "task": "Mock task"})
    )

    with patch(
        "src.mighty_mouse.orchestrator.mighty_mouse_agent._REPO_ROOT",
        str(tmp_path),
    ), patch(
        "src.mighty_mouse.orchestrator.mighty_mouse_agent.GeminiClient"
    ) as MockClient:
        mock_instance = MagicMock()
        mock_instance.generate_content.return_value = (
            "```python:hello.py\nprint('hello')\n```"
        )
        mock_instance.last_metadata = {}
        MockClient.return_value = mock_instance

        _solve_inner(
            str(p_cfg_path),
            str(task_input),
            feedback_str="Previous Pytest failed",
            temperature=0.45,
            workspace=str(workspace),
        )

        # Assert GeminiClient was instantiated with temperature=0.45
        MockClient.assert_called_once()
        config_passed = MockClient.call_args[1]["config"]
        assert config_passed.get("temperature") == 0.45

        # Assert generate_content received XML feedback and disallowed patterns
        args = mock_instance.generate_content.call_args[0]
        user_prompt = args[1]
        assert "<execution_feedback>" in user_prompt
        assert "Previous Pytest failed" in user_prompt
        assert "<disallowed_patterns>" in user_prompt

    assert not (tmp_path / "configs").exists()
    assert not (tmp_path / "tasks").exists()
