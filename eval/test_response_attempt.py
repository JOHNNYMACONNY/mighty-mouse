from dataclasses import fields

import pytest

from src.mighty_mouse.orchestrator.response_attempt import (
    ResponseAttemptContext,
    execute_response_attempt,
)


def test_response_attempt_context_stays_narrow():
    assert [field.name for field in fields(ResponseAttemptContext)] == [
        "system_prompt",
        "user_prompt",
        "task_id",
        "attempt",
        "max_attempts",
        "workspace_root",
        "allowed_delete_paths",
    ]


def test_response_attempt_owns_provider_and_schema_retries(tmp_path):
    events = []
    responses = iter(
        [
            RuntimeError("temporary provider failure"),
            "plain response",
            "valid response",
        ]
    )
    sleep_calls = []

    def provider(context, usage_history):
        events.append(("provider", context.attempt, context.user_prompt))
        response = next(responses)
        if isinstance(response, BaseException):
            raise response
        usage_history.append({"attempt": context.attempt})
        events.append(("usage", context.attempt))
        return response

    def parser(response, context):
        events.append(("parser", response, context.attempt))
        return [] if response == "plain response" else ["answer.py"]

    result = execute_response_attempt(
        ResponseAttemptContext(
            system_prompt="system",
            user_prompt="user",
            task_id="task",
            attempt=1,
            max_attempts=3,
            workspace_root=str(tmp_path),
        ),
        provider,
        parser,
        sleep_fn=sleep_calls.append,
    )

    assert result.failed is False
    assert result.output_paths == ["answer.py"]
    assert result.usage_history == [{"attempt": 2}, {"attempt": 3}]
    assert result.next_attempt == 4
    assert result.schema_error is False
    assert sleep_calls == [2]
    assert [event[:2] for event in events] == [
        ("provider", 1),
        ("provider", 2),
        ("usage", 2),
        ("parser", "plain response"),
        ("provider", 3),
        ("usage", 3),
        ("parser", "valid response"),
    ]
    assert "CRITICAL ERROR: No code blocks" in events[4][2]


def test_response_attempt_parser_errors_propagate_without_retry(tmp_path):
    provider_calls = []
    sleep_calls = []

    def provider(context, usage_history):
        provider_calls.append(context.attempt)
        usage_history.append({"attempt": context.attempt})
        return "response"

    def parser(_response, _context):
        raise ValueError("parser failed")

    with pytest.raises(ValueError, match="parser failed"):
        execute_response_attempt(
            ResponseAttemptContext(
                system_prompt="system",
                user_prompt="user",
                task_id="task",
                attempt=1,
                max_attempts=2,
                workspace_root=str(tmp_path),
            ),
            provider,
            parser,
            sleep_fn=sleep_calls.append,
        )

    assert provider_calls == [1]
    assert sleep_calls == []


def test_response_attempt_planner_bypasses_parser(tmp_path):
    def provider(context, usage_history):
        usage_history.append({"attempt": context.attempt})
        return "planner response"

    result = execute_response_attempt(
        ResponseAttemptContext(
            system_prompt="system",
            user_prompt="user",
            task_id="task",
            attempt=1,
            max_attempts=2,
            workspace_root=str(tmp_path),
        ),
        provider,
        None,
    )

    assert result.response == "planner response"
    assert result.output_paths == []
    assert result.usage_history == [{"attempt": 1}]
