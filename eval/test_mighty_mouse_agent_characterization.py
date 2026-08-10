import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.mighty_mouse.orchestrator.mighty_mouse_agent as agent


@pytest.fixture
def agent_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "provider: sim\n"
        "allow_simulation: true\n"
        "prompt_segments: []\n"
    )
    workspace = tmp_path / "workspace"

    def run(
        task_data,
        responses,
        *,
        stage="unified",
        plan_file=None,
        skills_result=None,
    ):
        task_file = tmp_path / "task.json"
        task_file.write_text(json.dumps(task_data))

        client = MagicMock()
        client.generate_content.side_effect = list(responses)
        client.last_metadata = {
            "usage": {"total_tokens": 11},
            "latency_seconds": 0.01,
        }
        client_factory = MagicMock(return_value=client)

        monkeypatch.setattr(agent, "GeminiClient", client_factory)
        monkeypatch.setattr(agent, "_REPO_ROOT", str(tmp_path))
        sleep_calls = []
        monkeypatch.setattr(agent.time, "sleep", sleep_calls.append)
        monkeypatch.setattr(agent.time, "time", lambda: 1700000000)
        if skills_result is not None:
            def fake_load_skills(**_):
                return skills_result

            monkeypatch.setattr(agent, "_load_skills", fake_load_skills)

        agent._solve_inner(
            str(config_file),
            str(task_file),
            workspace=str(workspace),
            stage=stage,
            plan_file=str(plan_file) if plan_file else None,
        )

        metadata_path = workspace / "logs" / "last_agent_run.json"
        metadata = json.loads(metadata_path.read_text())
        return SimpleNamespace(
            client=client,
            client_factory=client_factory,
            metadata=metadata,
            raw_logs=sorted(
                (tmp_path / "logs" / "raw_responses").glob("*.txt")
            ),
            sleep_calls=sleep_calls,
            task_file=task_file,
            workspace=workspace,
        )

    return SimpleNamespace(
        config_file=config_file,
        workspace=workspace,
        run=run,
        root=tmp_path,
    )


def test_provider_retry_then_success_preserves_success_only_usage(agent_env):
    result = agent_env.run(
        {
            "id": "provider_retry",
            "task": "write answer",
            "expected_files": ["answer.py"],
        },
        [
            RuntimeError("temporary provider failure"),
            "```python:answer.py\nprint('ok')\n```",
        ],
    )

    assert result.client.generate_content.call_count == 2
    assert result.sleep_calls == [2]
    assert result.metadata["attempts"] == 1
    assert len(result.metadata["usage_history"]) == 1
    assert result.metadata["pass_type"] == "clean"
    assert result.metadata["output_files"] == ["answer.py"]
    assert [path.name for path in result.raw_logs] == [
        "raw_provider_retry_attempt_2_1700000000.txt"
    ]


def test_provider_retry_exhaustion_records_failure_without_usage(agent_env):
    result = agent_env.run(
        {"id": "provider_exhausted", "task": "write answer"},
        [RuntimeError("first failure"), RuntimeError("terminal failure")],
    )

    assert result.client.generate_content.call_count == 2
    assert result.sleep_calls == [2]
    assert result.metadata["attempts"] == 0
    assert result.metadata["usage_history"] == [result.client.last_metadata]
    assert result.metadata["pass_type"] == "failed"
    assert result.metadata["output_files"] == []
    assert result.raw_logs == []


@pytest.mark.parametrize(
    ("responses", "pass_type", "schema_error", "expected_attempts"),
    [
        (
            ["plain response", "```python:schema.py\nvalue = 1\n```"],
            "clean",
            False,
            2,
        ),
        (["plain response", "still plain"], "failed", True, 2),
    ],
)
def test_schema_retry_state_transitions(
    agent_env,
    responses,
    pass_type,
    schema_error,
    expected_attempts,
):
    result = agent_env.run(
        {
            "id": "schema_task",
            "task": "write schema file",
            "expected_files": ["schema.py"],
        },
        responses,
    )

    assert result.client.generate_content.call_count == expected_attempts
    assert result.metadata["attempts"] == expected_attempts
    assert result.metadata["pass_type"] == pass_type
    assert result.metadata["schema_error"] is schema_error
    second_prompt = result.client.generate_content.call_args_list[1].args[1]
    assert "CRITICAL ERROR: No code blocks" in second_prompt


def test_coverage_recovery_records_second_attempt_success(agent_env):
    result = agent_env.run(
        {
            "id": "coverage_task",
            "task": "write both files",
            "expected_files": ["first.py", "second.py"],
        },
        [
            "```python:first.py\nfirst = True\n```",
            "```python:second.py\nsecond = True\n```",
        ],
    )

    assert result.client.generate_content.call_count == 2
    assert result.metadata["attempts"] == 2
    assert result.metadata["coverage_recovery_triggered"] is True
    assert result.metadata["coverage_missing_files"] == ["second.py"]
    assert result.metadata["coverage_recovery_attempts"] == 1
    assert result.metadata["coverage_recovery_success"] is True
    assert result.metadata["coverage_recovery_disallowed_reason"] is None
    assert set(result.metadata["output_files"]) == {"first.py", "second.py"}


@pytest.mark.parametrize(
    ("task_data", "responses", "skills_result", "reason"),
    [
        (
            {
                "id": "deletable_missing",
                "expected_files": ["obsolete.py"],
                "deletable_files": ["obsolete.py"],
            },
            ["```python:other.py\nvalue = 1\n```"],
            None,
            "DELETABLE_FILE_EXCLUSION",
        ),
        (
            {"id": "obs_task_conflict_case", "expected_files": ["missing.py"]},
            ["```python:other.py\nvalue = 1\n```"],
            None,
            "CONFLICT_ROUTING_VALIDATION_TASK",
        ),
        (
            {"id": "conflict_task", "expected_files": ["missing.py"]},
            ["```python:other.py\nvalue = 1\n```"],
            (
                [],
                [],
                {
                    "conflict_detected": True,
                    "conflicting_skill_ids": ["skill-a"],
                },
            ),
            "CONFLICT_DETECTED",
        ),
        (
            {"id": "second_omission", "expected_files": ["missing.py"]},
            [
                "```python:first.py\nvalue = 1\n```",
                "```python:second.py\nvalue = 2\n```",
            ],
            None,
            "MAX_ATTEMPTS_REACHED",
        ),
    ],
)
def test_coverage_recovery_disallowed_cases(
    agent_env,
    task_data,
    responses,
    skills_result,
    reason,
):
    result = agent_env.run(task_data, responses, skills_result=skills_result)

    assert result.metadata["pass_type"] == "failed"
    assert result.metadata["coverage_recovery_disallowed_reason"] == reason


def test_parser_value_error_propagates(agent_env, monkeypatch):
    def raise_parser_error(*args, **kwargs):
        raise ValueError("malformed parser response")

    monkeypatch.setattr(
        agent.ResponseParser,
        "parse_and_write",
        raise_parser_error,
    )
    task_data = {"id": "parser_error", "task": "parse output"}
    task_file = agent_env.root / "task.json"
    task_file.write_text(json.dumps(task_data))
    client = MagicMock()
    client.generate_content.return_value = (
        "```python:answer.py\nvalue = 1\n```"
    )
    client.last_metadata = {}
    monkeypatch.setattr(agent, "GeminiClient", MagicMock(return_value=client))
    monkeypatch.setattr(agent, "_REPO_ROOT", str(agent_env.root))

    with pytest.raises(ValueError, match="malformed parser response"):
        agent._solve_inner(
            str(agent_env.config_file),
            str(task_file),
            workspace=str(agent_env.workspace),
        )


def test_planner_writes_plan_without_parser(agent_env, monkeypatch):
    plan_file = agent_env.root / "plans" / "stage1.md"
    parse_and_write = MagicMock()
    monkeypatch.setattr(
        agent.ResponseParser,
        "parse_and_write",
        parse_and_write,
    )

    result = agent_env.run(
        {"id": "planner_task", "task": "plan work"},
        ["<plan>\n1. Inspect\n2. Implement\n</plan>"],
        stage="planner",
        plan_file=plan_file,
    )

    assert plan_file.read_text().startswith("<plan>")
    parse_and_write.assert_not_called()
    assert result.client.generate_content.call_count == 1
    assert result.metadata["pass_type"] == "clean"


def test_written_and_deleted_classification_persists_metadata(agent_env):
    obsolete = agent_env.workspace / "obsolete.py"
    obsolete.parent.mkdir(parents=True, exist_ok=True)
    obsolete.write_text("old = True\n")
    result = agent_env.run(
        {
            "id": "classification_task",
            "task": "write and delete files",
            "expected_files": ["answer.py"],
            "deletable_files": ["obsolete.py"],
        },
        [
            "```python:answer.py\nanswer = True\n```\n"
            "```delete:obsolete.py\n\n```"
        ],
    )

    assert (result.workspace / "answer.py").exists()
    assert not obsolete.exists()
    assert result.metadata["written_files"] == ["answer.py"]
    assert result.metadata["deleted_files"] == ["obsolete.py"]
    assert set(result.metadata["output_files"]) == {"answer.py", "obsolete.py"}


def test_generation_attempt_success_captures_usage_and_raw_response(
    tmp_path,
    monkeypatch,
):
    client = MagicMock()
    response = "raw provider response"
    client.generate_content.return_value = response
    client.last_metadata = {"usage": {"total_tokens": 7}}
    usage_history = []
    monkeypatch.setattr(agent, "_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(agent.time, "time", lambda: 1700000001)

    returned = agent._execute_generation_attempt(
        client,
        "system prompt",
        "user prompt",
        task_id="attempt_task",
        attempt=1,
        usage_history=usage_history,
    )

    assert returned == response
    client.generate_content.assert_called_once_with(
        "system prompt",
        "user prompt",
    )
    assert usage_history == [client.last_metadata]
    raw_log = (
        tmp_path
        / "logs"
        / "raw_responses"
        / "raw_attempt_task_attempt_1_1700000001.txt"
    )
    assert raw_log.read_text() == response


def test_generation_attempt_provider_error_leaves_usage_and_logs_unchanged(
    tmp_path,
    monkeypatch,
):
    client = MagicMock()
    client.generate_content.side_effect = RuntimeError("provider unavailable")
    client.last_metadata = {"usage": {"total_tokens": 7}}
    usage_history = []
    monkeypatch.setattr(agent, "_REPO_ROOT", str(tmp_path))

    with pytest.raises(RuntimeError, match="provider unavailable"):
        agent._execute_generation_attempt(
            client,
            "system prompt",
            "user prompt",
            task_id="provider_error",
            attempt=1,
            usage_history=usage_history,
        )

    assert usage_history == []
    assert not (tmp_path / "logs").exists()


def test_generation_attempt_raw_log_error_preserves_usage_append_order(
    tmp_path,
    monkeypatch,
):
    client = MagicMock()
    client.generate_content.return_value = "successful response"
    client.last_metadata = {"usage": {"total_tokens": 7}}
    usage_history = []

    def fail_raw_log(path, mode="r", *args, **kwargs):
        if "raw_responses" in str(path):
            raise OSError("raw log unavailable")
        return open(path, mode, *args, **kwargs)

    monkeypatch.setattr(agent, "_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(agent, "open", fail_raw_log, raising=False)

    with pytest.raises(OSError, match="raw log unavailable"):
        agent._execute_generation_attempt(
            client,
            "system prompt",
            "user prompt",
            task_id="raw_log_error",
            attempt=1,
            usage_history=usage_history,
        )

    assert usage_history == [client.last_metadata]
    assert not list((tmp_path / "logs" / "raw_responses").glob("*.txt"))
