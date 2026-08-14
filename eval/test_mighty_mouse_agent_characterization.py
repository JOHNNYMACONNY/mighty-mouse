import builtins
import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import src.mighty_mouse.orchestrator.mighty_mouse_agent as agent


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
    assert result.metadata["coverage_missing_files"] == []
    assert result.metadata["coverage_recovery_attempts"] == 0
    assert result.metadata["coverage_recovery_triggered"] is False
    assert result.metadata["coverage_recovery_success"] is False
    assert result.metadata["coverage_recovery_disallowed_reason"] is None
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
    recovery_prompt = result.client.generate_content.call_args_list[1].args[1]
    assert "- second.py" in recovery_prompt
    assert "- first.py" not in recovery_prompt
    assert "Only provide the missing file blocks." in recovery_prompt


def test_empty_expected_files_follow_clean_no_recovery_path(agent_env):
    result = agent_env.run(
        {
            "id": "empty_expected_files",
            "expected_files": [],
        },
        ["```python:answer.py\nanswer = True\n```"],
    )

    assert result.client.generate_content.call_count == 1
    assert result.metadata["pass_type"] == "clean"
    assert result.metadata["output_files"] == ["answer.py"]
    assert result.metadata["coverage_missing_files"] == []
    assert result.metadata["coverage_recovery_attempts"] == 0
    assert result.metadata["coverage_recovery_triggered"] is False
    assert result.metadata["coverage_recovery_success"] is False
    assert result.metadata["coverage_recovery_disallowed_reason"] is None


def test_schema_failure_stops_before_coverage_policy(agent_env):
    result = agent_env.run(
        {
            "id": "schema_before_coverage",
            "expected_files": ["missing.py"],
        },
        ["plain response", "still plain"],
    )

    assert result.client.generate_content.call_count == 2
    assert result.metadata["pass_type"] == "failed"
    assert result.metadata["schema_error"] is True
    assert result.metadata["coverage_missing_files"] == []
    assert result.metadata["coverage_recovery_attempts"] == 0
    assert result.metadata["coverage_recovery_triggered"] is False
    assert result.metadata["coverage_recovery_disallowed_reason"] is None


@pytest.mark.parametrize(
    ("task_data", "skills_result", "reason"),
    [
        (
            {
                "id": "obs_task_conflict_overlap",
                "tags": ["conflict"],
                "expected_files": ["missing.py"],
                "deletable_files": ["missing.py"],
            },
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
            {
                "id": "obs_task_rejected_overlap",
                "tags": ["routing"],
                "expected_files": ["missing.py"],
                "deletable_files": ["missing.py"],
            },
            (
                [],
                [{"id": "skill-a", "injection_reason": "CONFLICT_REJECTED"}],
                {"conflict_detected": False, "conflicting_skill_ids": []},
            ),
            "CONFLICT_REJECTED",
        ),
        (
            {
                "id": "obs_task_routing_overlap",
                "tags": ["routing"],
                "expected_files": ["missing.py"],
                "deletable_files": ["missing.py"],
            },
            (
                [],
                [{"id": "skill-a"}],
                {"conflict_detected": False, "conflicting_skill_ids": []},
            ),
            "CONFLICT_ROUTING_VALIDATION_TASK",
        ),
    ],
)
def test_coverage_rejection_precedence(
    agent_env, task_data, skills_result, reason
):
    result = agent_env.run(
        task_data,
        ["```python:other.py\nvalue = 1\n```"],
        skills_result=skills_result,
    )

    assert result.metadata["pass_type"] == "failed"
    assert result.metadata["coverage_missing_files"] == ["missing.py"]
    assert result.metadata["coverage_recovery_disallowed_reason"] == reason
    assert result.metadata["coverage_recovery_attempts"] == 0


def test_schema_retry_then_coverage_recovery_reaches_third_attempt(agent_env):
    result = agent_env.run(
        {
            "id": "schema_then_coverage",
            "expected_files": ["first.py", "second.py"],
        },
        [
            "plain response",
            "```python:first.py\nfirst = True\n```",
            "```python:second.py\nsecond = True\n```",
        ],
    )

    assert result.client.generate_content.call_count == 3
    assert result.metadata["attempts"] == 3
    assert result.metadata["pass_type"] == "recovered"
    assert result.metadata["coverage_recovery_triggered"] is True
    assert result.metadata["coverage_missing_files"] == ["second.py"]
    assert result.metadata["coverage_recovery_attempts"] == 1
    assert result.metadata["coverage_recovery_success"] is True
    assert result.metadata["coverage_recovery_disallowed_reason"] is None
    assert len(result.metadata["usage_history"]) == 3
    assert set(result.metadata["output_files"]) == {"first.py", "second.py"}

    recovery_prompt = result.client.generate_content.call_args_list[2].args[1]
    assert "CRITICAL OMISSION DETECTED" in recovery_prompt
    assert "- second.py" in recovery_prompt
    assert "Only provide the missing file blocks." in recovery_prompt


def test_response_attempt_order_preserves_usage_logs_and_parser_invocation(
    agent_env,
    monkeypatch,
):
    events = []
    parse_results = iter([[], ["answer.py"]])

    def apply_response(request):
        events.append(("application", request.raw_response))
        return next(parse_results)

    def record_open(path, mode="r", *args, **kwargs):
        if "raw_responses" in str(path) and "w" in mode:
            events.append(("raw_log_open", Path(path).name))
        return builtins.open(path, mode, *args, **kwargs)

    original_execute_generation_attempt = agent._execute_generation_attempt

    class RecordingUsageHistory:
        def __init__(self, delegate):
            self._delegate = delegate

        def append(self, metadata):
            events.append(("usage_append", metadata["usage"]["total_tokens"]))
            self._delegate.append(metadata)

    def record_generation_attempt(*args, **kwargs):
        usage_history = kwargs["usage_history"]
        kwargs["usage_history"] = RecordingUsageHistory(usage_history)
        return original_execute_generation_attempt(*args, **kwargs)

    application = MagicMock(side_effect=apply_response)
    monkeypatch.setattr(agent, "apply_response", application)
    monkeypatch.setattr(agent, "open", record_open, raising=False)
    monkeypatch.setattr(
        agent,
        "_execute_generation_attempt",
        record_generation_attempt,
    )
    metadata_sequence = [
        {"usage": {"total_tokens": 3}, "latency_seconds": 0.03},
        {"usage": {"total_tokens": 5}, "latency_seconds": 0.05},
    ]

    result = agent_env.run(
        {
            "id": "ordered_attempts",
            "task": "write answer",
        },
        [
            "plain response",
            "```python:answer.py\nanswer = True\n```",
        ],
        metadata_sequence=metadata_sequence,
        event_log=events,
    )

    assert events == [
        ("provider", "plain response"),
        ("usage_append", 3),
        ("raw_log_open", "raw_ordered_attempts_attempt_1_1700000000.txt"),
        ("application", "plain response"),
        ("provider", "```python:answer.py\nanswer = True\n```"),
        ("usage_append", 5),
        ("raw_log_open", "raw_ordered_attempts_attempt_2_1700000000.txt"),
        ("application", "```python:answer.py\nanswer = True\n```"),
    ]
    assert result.metadata["usage_history"] == metadata_sequence
    assert result.metadata["attempts"] == 2
    assert result.client.generate_content.call_count == 2
    assert application.call_count == 2
    assert [path.name for path in result.raw_logs] == [
        "raw_ordered_attempts_attempt_1_1700000000.txt",
        "raw_ordered_attempts_attempt_2_1700000000.txt",
    ]


@pytest.mark.parametrize(
    (
        "task_data",
        "responses",
        "skills_result",
        "reason",
        "expected_calls",
        "expected_recovery_triggered",
    ),
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
            1,
            False,
        ),
        (
            {"id": "obs_task_conflict_case", "expected_files": ["missing.py"]},
            ["```python:other.py\nvalue = 1\n```"],
            None,
            "CONFLICT_ROUTING_VALIDATION_TASK",
            1,
            False,
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
            1,
            False,
        ),
        (
            {"id": "second_omission", "expected_files": ["missing.py"]},
            [
                "```python:first.py\nvalue = 1\n```",
                "```python:second.py\nvalue = 2\n```",
            ],
            None,
            "MAX_ATTEMPTS_REACHED",
            2,
            True,
        ),
        (
            {
                "id": "multiple_missing_files",
                "expected_files": ["third.py", "first.py", "second.py"],
            },
            [
                "```python:other.py\nvalue = 1\n```",
                "```python:another.py\nvalue = 2\n```",
            ],
            None,
            "MAX_ATTEMPTS_REACHED",
            2,
            True,
        ),
    ],
)
def test_coverage_recovery_disallowed_cases(
    agent_env,
    task_data,
    responses,
    skills_result,
    reason,
    expected_calls,
    expected_recovery_triggered,
):
    result = agent_env.run(task_data, responses, skills_result=skills_result)

    assert result.metadata["pass_type"] == "failed"
    assert result.metadata["coverage_recovery_disallowed_reason"] == reason
    assert (
        result.metadata["coverage_recovery_triggered"]
        is expected_recovery_triggered
    )
    assert result.metadata["coverage_recovery_success"] is False
    assert result.client.generate_content.call_count == expected_calls
    actual_missing_files = result.metadata["coverage_missing_files"]
    assert actual_missing_files == task_data["expected_files"]
    assert result.metadata["coverage_recovery_attempts"] == expected_calls - 1


def test_coverage_recovery_does_not_duplicate_provider_or_parser_side_effects(
    agent_env,
    monkeypatch,
):
    events = []
    application_requests = []

    def apply_response(request):
        application_requests.append(request)
        events.append(("application", request.raw_response))
        if "first.py" in request.raw_response:
            return ["first.py"]
        return ["second.py"]

    monkeypatch.setattr(
        agent,
        "apply_response",
        apply_response,
    )
    result = agent_env.run(
        {
            "id": "coverage_side_effects",
            "expected_files": ["first.py", "second.py"],
        },
        [
            "```python:first.py\nvalue = 1\n```",
            "```python:second.py\nvalue = 2\n```",
        ],
        event_log=events,
    )

    assert events == [
        ("provider", "```python:first.py\nvalue = 1\n```"),
        ("application", "```python:first.py\nvalue = 1\n```"),
        ("provider", "```python:second.py\nvalue = 2\n```"),
        ("application", "```python:second.py\nvalue = 2\n```"),
    ]
    assert result.client.generate_content.call_count == 2
    assert [
        request.policy.workspace_root for request in application_requests
    ] == [str(agent_env.workspace), str(agent_env.workspace)]
    assert all(
        request.policy.allowed_delete_paths == ()
        and request.policy.max_file_bytes == 100_000
        and request.policy.system_mode is False
        and request.policy.strict_code_hygiene is False
        for request in application_requests
    )
    assert result.metadata["coverage_recovery_attempts"] == 1
    assert result.metadata["pass_type"] == "recovered"


def test_pre_run_hygiene_removes_stale_root_python_before_classification(
    agent_env,
):
    stale_file = agent_env.root / "stale_ghost.py"
    stale_file.write_text("stale = True\n")

    result = agent_env.run(
        {
            "id": "hygiene_before_classification",
            "expected_files": ["answer.py"],
        },
        ["```python:answer.py\nanswer = True\n```"],
    )

    assert not stale_file.exists()
    assert result.metadata["stale_ghost_files_removed_pre_run"] == 1
    assert result.metadata["written_files"] == ["answer.py"]
    assert result.metadata["deleted_files"] == []


def test_parser_value_error_propagates(agent_env, monkeypatch):
    def raise_application_error(*args, **kwargs):
        raise ValueError("malformed parser response")

    monkeypatch.setattr(agent, "apply_response", raise_application_error)
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
    apply_response = MagicMock()
    monkeypatch.setattr(agent, "apply_response", apply_response)

    result = agent_env.run(
        {"id": "planner_task", "task": "plan work"},
        ["<plan>\n1. Inspect\n2. Implement\n</plan>"],
        stage="planner",
        plan_file=plan_file,
    )

    assert plan_file.read_text().startswith("<plan>")
    apply_response.assert_not_called()
    assert result.client.generate_content.call_count == 1
    assert result.metadata["pass_type"] == "clean"


def test_coder_prompt_preserves_plan_file_and_feedback(agent_env):
    plan_file = agent_env.root / "plans" / "stage1.md"
    plan_file.parent.mkdir(parents=True)
    plan_file.write_text("<plan>Keep response contract stable</plan>")

    result = agent_env.run(
        {"id": "coder_feedback_plan", "task": "implement plan"},
        ["```python:answer.py\nanswer = True\n```"],
        stage="coder",
        plan_file=plan_file,
        feedback_str="Previous attempt missed parser ordering",
    )

    user_prompt = result.client.generate_content.call_args.args[1]
    assert "<stage1_blueprint>" in user_prompt
    assert "<plan>Keep response contract stable</plan>" in user_prompt
    assert "<execution_feedback>" in user_prompt
    assert "Previous attempt missed parser ordering" in user_prompt
    assert result.metadata["feedback_supplied"] is True
    assert (result.workspace / "answer.py").exists()


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
    events = []
    real_open = open

    class RecordingUsageHistory:
        def append(self, metadata):
            events.append(("usage_append", metadata["usage"]["total_tokens"]))
            usage_history.append(metadata)

    recorded_usage_history = RecordingUsageHistory()

    class FailingRawLog:
        def __init__(self, handle):
            self._handle = handle

        def __enter__(self):
            self._handle.__enter__()
            events.append(("raw_log_open", "raw_log_error.txt"))
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            return self._handle.__exit__(exc_type, exc_value, traceback)

        def write(self, _response):
            events.append(("raw_log_write", "raw_log_error.txt"))
            raise OSError("raw log unavailable")

    def fail_raw_log(path, mode="r", *args, **kwargs):
        if "raw_responses" in str(path):
            return FailingRawLog(real_open(path, mode, *args, **kwargs))
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
            usage_history=recorded_usage_history,
        )

    assert usage_history == [client.last_metadata]
    assert [event[0] for event in events] == [
        "usage_append",
        "raw_log_open",
        "raw_log_write",
    ]
    raw_logs = list((tmp_path / "logs" / "raw_responses").glob("*.txt"))
    assert len(raw_logs) == 1
    assert raw_logs[0].read_text() == ""
