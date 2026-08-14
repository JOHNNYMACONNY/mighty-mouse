import inspect
from dataclasses import fields
from pathlib import Path

import pytest

import src.mighty_mouse.orchestrator.mighty_mouse_agent as agent
from src.mighty_mouse.orchestrator.agent_execution import (
    _AgentExecutionRequest,
    _execute_agent_execution,
)
from src.mighty_mouse.orchestrator.response_attempt import (
    ResponseAttemptContext,
    ResponseAttemptResult,
)


def _request(tmp_path, *, expected_files=()):
    return _AgentExecutionRequest(
        response_attempt_context=ResponseAttemptContext(
            system_prompt="system",
            user_prompt="initial",
            task_id="agent_execution_test",
            attempt=1,
            max_attempts=2,
            workspace_root=str(tmp_path),
            allowed_delete_paths=("obsolete.py",),
        ),
        expected_files=tuple(expected_files),
        conflict_detected=False,
        injection_reason=None,
        is_conflict_routing_validation=False,
        deletable_expected_files=(),
    )


def test_agent_execution_owns_coverage_recovery_and_passes_opaque_adapter(
    tmp_path,
):
    runner_calls = []
    application_calls = []
    responses = iter(
        [
            "first response",
            "second response",
        ]
    )

    def response_application(response, context):
        application_calls.append((response, context.attempt))
        return ["first.py"] if context.attempt == 1 else ["second.py"]

    def response_attempt_runner(context, parser_adapter):
        runner_calls.append(
            (
                context.attempt,
                context.max_attempts,
                parser_adapter is response_application,
            )
        )
        response = next(responses)
        output_paths = parser_adapter(response, context)
        return ResponseAttemptResult(
            response=response,
            output_paths=list(output_paths),
            usage_history=[{"attempt": context.attempt}],
            schema_error=False,
            next_attempt=context.attempt + 1,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    outcome = _execute_agent_execution(
        _request(tmp_path, expected_files=("first.py", "second.py")),
        response_attempt_runner=response_attempt_runner,
        response_application_adapter=response_application,
    )

    assert runner_calls == [(1, 2, True), (2, 3, True)]
    assert application_calls == [("first response", 1), ("second response", 2)]
    assert outcome.output_paths == ("first.py", "second.py")
    assert outcome.coverage_recovery_attempts == 1
    assert outcome.coverage_recovery_triggered is True
    assert outcome.coverage_missing_files == ("second.py",)
    assert outcome.coverage_recovery_success is True
    assert outcome.pass_type == "recovered"
    assert "attempts" not in {field.name for field in fields(outcome)}


def test_agent_execution_planner_adapter_skips_coverage_policy(tmp_path):
    request = _request(tmp_path, expected_files=("not_for_planner.py",))
    runner_calls = []

    def response_attempt_runner(context, parser_adapter):
        runner_calls.append((context.attempt, parser_adapter))
        return ResponseAttemptResult(
            response="<plan>keep parser opaque</plan>",
            output_paths=[],
            usage_history=[{"attempt": 1}],
            schema_error=False,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    outcome = _execute_agent_execution(
        request,
        response_attempt_runner=response_attempt_runner,
        response_application_adapter=None,
    )

    assert runner_calls == [(1, None)]
    assert outcome.response == "<plan>keep parser opaque</plan>"
    assert outcome.coverage_missing_files == ()
    assert outcome.coverage_recovery_attempts == 0
    assert outcome.pass_type == "clean"


def test_solve_normalizes_paths_and_restores_cwd(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    observed = {}

    def fake_solve_inner(
        p_cfg_path,
        task_input,
        feedback_str=None,
        workspace=None,
        explicit_skills=None,
        temperature=None,
        stage="unified",
        plan_file=None,
    ):
        observed.update(
            p_cfg_path=p_cfg_path,
            task_input=task_input,
            workspace=workspace,
            cwd=Path.cwd(),
        )
        return "solve result"

    monkeypatch.setattr(agent, "_solve_inner", fake_solve_inner)
    original_cwd = Path.cwd()

    result = agent.solve(
        "relative-config.yaml",
        "relative-task.json",
        workspace=str(workspace),
    )

    assert result == "solve result"
    assert observed["p_cfg_path"] == str(
        Path("relative-config.yaml").resolve()
    )
    assert observed["task_input"] == str(
        Path("relative-task.json").resolve()
    )
    assert observed["workspace"] == str(workspace.resolve())
    assert observed["cwd"] == workspace.resolve()
    assert Path.cwd() == original_cwd


def test_solve_restores_cwd_when_inner_execution_fails(monkeypatch, tmp_path):
    workspace = tmp_path / "workspace"
    original_cwd = Path.cwd()

    def fail_solve_inner(*args, **kwargs):
        assert Path.cwd() == workspace.resolve()
        raise RuntimeError("execution failed")

    monkeypatch.setattr(agent, "_solve_inner", fail_solve_inner)

    with pytest.raises(RuntimeError, match="execution failed"):
        agent.solve("config.yaml", "task.json", workspace=str(workspace))

    assert Path.cwd() == original_cwd
    assert list(inspect.signature(agent.solve).parameters) == [
        "p_cfg_path",
        "task_input",
        "feedback_str",
        "workspace",
        "explicit_skills",
        "temperature",
        "stage",
        "plan_file",
    ]
