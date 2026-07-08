import json
import sys
from pathlib import Path

import pytest

from mighty_mouse.experiments.local_agent import (
    AgentBudget,
    WorkspaceTools,
    build_tool_definitions,
    run_agent_condition,
)


class ScriptedClient:
    model = "scripted-model"

    def __init__(self, messages):
        self.messages = iter(messages)

    def chat(self, messages, tools, **kwargs):
        return next(self.messages), {
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "wall_seconds": 0.01,
        }


def tool_call(name, **arguments):
    return {"role": "assistant", "content": "", "tool_calls": [{"function": {"name": name, "arguments": arguments}}]}


def task():
    return {
        "id": "pilot-low",
        "description": "Set value.py VALUE to 42 and verify it.",
        "complexity": "low",
        "allowed_paths": ["value.py"],
        "ignored_paths": ["__pycache__"],
        "checks": {"tests": [sys.executable, "-c", "from value import VALUE; assert VALUE == 42"]},
        "check_timeout_seconds": 10,
    }


def test_workspace_tools_reject_escape_and_unlisted_writes(tmp_path):
    tools = WorkspaceTools(tmp_path, allowed_paths=["value.py"], checks={}, command_timeout_seconds=10)

    with pytest.raises(ValueError, match="escapes workspace"):
        tools.read_file("../secret")
    with pytest.raises(PermissionError, match="outside allowed paths"):
        tools.write_file("extra.py", "pass\n")


def test_workspace_tools_do_not_follow_external_symlinks(tmp_path):
    outside = tmp_path.parent / "outside-secret.txt"
    outside.write_text("secret")
    (tmp_path / "linked-secret.txt").symlink_to(outside)
    tools = WorkspaceTools(tmp_path, allowed_paths=["value.py"], checks={}, command_timeout_seconds=10)

    assert "linked-secret.txt" not in tools.list_files()["files"]
    assert tools.search_text("secret")["matches"] == []
    with pytest.raises(ValueError, match="escapes workspace"):
        tools.read_file("linked-secret.txt")


def test_run_check_uses_an_argv_allowlist(tmp_path):
    tools = WorkspaceTools(
        tmp_path,
        allowed_paths=["value.py"],
        checks={"tests": [sys.executable, "-c", "print('ok')"]},
        command_timeout_seconds=10,
    )

    assert tools.run_check("tests")["passed"] is True
    with pytest.raises(ValueError, match="Unknown check_id"):
        tools.run_check("python -c malicious")


def test_tool_contract_exposes_exact_write_scope_and_check_ids():
    definitions = build_tool_definitions(["src/value.py"], {"tests": ["pytest"], "lint": ["ruff"]})
    functions = {definition["function"]["name"]: definition["function"] for definition in definitions}

    assert "src/value.py" in functions["write_file"]["description"]
    assert functions["run_check"]["parameters"]["properties"]["check_id"]["enum"] == ["lint", "tests"]


def test_agent_writes_checks_and_finishes_with_structured_evidence(tmp_path):
    client = ScriptedClient([
        tool_call("list_files", path="."),
        tool_call("write_file", path="value.py", content="VALUE = 42\n"),
        tool_call("run_check", check_id="tests"),
        tool_call("finish", summary="Implemented and verified VALUE."),
    ])

    result = run_agent_condition(
        client,
        tmp_path,
        task(),
        condition="gemma_raw",
        budget=AgentBudget(max_turns=5, max_tool_calls=5, max_wall_seconds=30),
    )

    assert result["passed"] is True
    assert result["stop_reason"] == "model_finished"
    assert result["changed_paths"] == ["value.py"]
    assert result["disallowed_changes"] == []
    assert result["acceptance"]["tests"]["passed"] is True
    assert result["usage"] == {
        "prompt_tokens": 40,
        "completion_tokens": 20,
        "model_seconds": pytest.approx(0.04),
        "total_tokens": 60,
    }
    json.dumps(result)


def test_external_acceptance_overrides_false_finish_claim(tmp_path):
    client = ScriptedClient([
        tool_call("write_file", path="value.py", content="VALUE = 7\n"),
        tool_call("finish", summary="Everything passes."),
    ])

    result = run_agent_condition(
        client,
        tmp_path,
        task(),
        condition="gemma_mighty_mouse",
        budget=AgentBudget(max_turns=3, max_tool_calls=3, max_wall_seconds=30),
    )

    assert result["passed"] is False
    assert result["acceptance"]["tests"]["passed"] is False


def test_hidden_acceptance_is_not_exposed_as_a_model_tool(tmp_path):
    hidden_task = task()
    hidden_task["checks"] = {"public_tests": [sys.executable, "-c", "pass"]}
    hidden_task["acceptance_checks"] = {
        "held_out_tests": [sys.executable, "-c", "from value import VALUE; assert VALUE == 42"]
    }
    captured_tools = []

    class CapturingClient(ScriptedClient):
        def chat(self, messages, tools, **kwargs):
            captured_tools.extend(tools)
            return super().chat(messages, tools, **kwargs)

    result = run_agent_condition(
        CapturingClient([tool_call("write_file", path="value.py", content="VALUE = 42\n"), tool_call("finish", summary="done")]),
        tmp_path,
        hidden_task,
        condition="gemma_raw",
        budget=AgentBudget(max_turns=3, max_tool_calls=3, max_wall_seconds=30),
    )

    run_check = next(tool for tool in captured_tools if tool["function"]["name"] == "run_check")
    assert run_check["function"]["parameters"]["properties"]["check_id"]["enum"] == ["public_tests"]
    assert "held_out_tests" not in json.dumps(captured_tools)
    assert result["acceptance"]["held_out_tests"]["passed"] is True


def test_declared_generated_artifacts_are_recorded_without_failing_scope(tmp_path):
    generated_task = task()
    generated_task["ignored_paths"].append(".test-cache")
    client = ScriptedClient([
        tool_call("write_file", path="value.py", content="VALUE = 42\n"),
        tool_call("finish", summary="done"),
    ])
    (tmp_path / ".test-cache").mkdir()
    (tmp_path / ".test-cache" / "before").write_text("old")

    class GeneratingClient(ScriptedClient):
        def chat(self, messages, tools, **kwargs):
            (tmp_path / ".test-cache" / "during").write_text("generated")
            return super().chat(messages, tools, **kwargs)

    result = run_agent_condition(
        GeneratingClient(client.messages),
        tmp_path,
        generated_task,
        condition="gemma_raw",
        budget=AgentBudget(max_turns=3, max_tool_calls=3, max_wall_seconds=30),
    )

    assert result["passed"] is True
    assert result["changed_paths"] == ["value.py"]
    assert ".test-cache/during" in result["ignored_generated_paths"]
    assert result["disallowed_changes"] == []


def test_condition_prompts_differ_only_by_mighty_mouse_protocol(tmp_path):
    captured = {}

    class CapturingClient(ScriptedClient):
        def __init__(self, condition):
            super().__init__([tool_call("finish", summary="done")])
            self.condition = condition

        def chat(self, messages, tools, **kwargs):
            captured[self.condition] = messages[0]["content"]
            return super().chat(messages, tools, **kwargs)

    for condition in ("gemma_raw", "gemma_mighty_mouse", "reference_raw"):
        run_agent_condition(
            CapturingClient(condition),
            tmp_path,
            task(),
            condition=condition,
            budget=AgentBudget(max_turns=1, max_tool_calls=1, max_wall_seconds=30),
        )

    assert captured["gemma_raw"] == captured["reference_raw"]
    assert "Mighty Mouse local-agent protocol" not in captured["gemma_raw"]
    assert "Mighty Mouse local-agent protocol" in captured["gemma_mighty_mouse"]
    assert "Writable paths: value.py" in captured["gemma_raw"]
    assert "Available check identifiers: tests" in captured["gemma_raw"]
