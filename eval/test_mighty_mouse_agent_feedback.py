def test_solve_inner_temperature_and_feedback(agent_env):
    result = agent_env.run(
        {"id": "mock_task_01", "task": "Mock task"},
        ["```python:hello.py\nprint('hello')\n```"],
        feedback_str="Previous Pytest failed",
        temperature=0.45,
    )

    result.client_factory.assert_called_once()
    config_passed = result.client_factory.call_args[1]["config"]
    assert config_passed.get("temperature") == 0.45

    args = result.client.generate_content.call_args[0]
    user_prompt = args[1]
    assert "<execution_feedback>" in user_prompt
    assert "Previous Pytest failed" in user_prompt
    assert "<disallowed_patterns>" in user_prompt

    assert not (agent_env.root / "configs").exists()
    assert not (agent_env.root / "tasks").exists()
