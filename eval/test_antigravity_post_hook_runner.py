"""Tests for Antigravity PostToolUse verification runner v1."""

from __future__ import annotations

import io
import json
from pathlib import Path
import subprocess
import sys
from typing import Any
from unittest.mock import patch

import pytest

from mighty_mouse.host.adapter import (
    ADAPTER_CONFIG_FILENAME,
    MCP_TOOL_CONTRACT_VERSION,
    HostAdapter,
)
from mighty_mouse.host.hooks import (
    HostHookResult,
    ResolvedHostHookEvent,
)
from mighty_mouse_mcp.antigravity_hooks import (
    POST_ACTION_VERIFY_ENV,
    evaluate_antigravity_post_tool_use,
    post_tool_use_main,
    run_antigravity_post_tool_use,
)
from mighty_mouse_mcp.server import _get_mcp_tool_signatures


def _setup_workspace_adapter_config(
    ws_path: Path,
    *,
    repository: str = "JOHNNYMACONNY/mighty-mouse",
    model_digest: str = "sha256:" + "a" * 64,
    model_class: str = "local-small",
    runtime_kind: str = "antigravity",
    runtime_version: str = "1.0.0",
    effective_context_limit: int = 32000,
    ollama_model: str | None = None,
    tool_signatures: dict[str, Any] | None = None,
    contract_version: int = MCP_TOOL_CONTRACT_VERSION,
) -> Path:
    """Create a valid .mighty-mouse/mcp-adapter.json in ws_path."""
    sigs = (
        tool_signatures
        if tool_signatures is not None
        else _get_mcp_tool_signatures()
    )
    state_dir = ws_path / ".mighty-mouse"
    state_dir.mkdir(parents=True, exist_ok=True)
    cfg = HostAdapter.build_adapter_config(
        repository=repository,
        model_digest=model_digest,
        model_class=model_class,
        effective_context_limit=effective_context_limit,
        runtime_kind=runtime_kind,
        runtime_version=runtime_version,
        ollama_model=ollama_model,
        tool_signatures=sigs,
        contract_version=contract_version,
    )
    config_file = state_dir / ADAPTER_CONFIG_FILENAME
    config_file.write_text(json.dumps(cfg), encoding="utf-8")
    return config_file


def test_post_tool_use_opt_in_write_success(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid write + opt-in -> verifier called once and passes."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
        "stepIdx": 1,
    }

    mock_verif = {
        "passed": True,
        "checks": [
            {
                "name": "tests",
                "passed": True,
                "output": "1 passed",
                "duration_sec": 0.5,
            }
        ],
        "summary": "Passed 1/1 verification checks.",
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ) as mock_rv:
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        mock_rv.assert_called_once_with(str(tmp_path))

        assert isinstance(eval_result, HostHookResult)
        assert eval_result.disposition == "continue"
        assert eval_result.reason_code == "verification_passed"
        assert eval_result.verification is not None
        assert eval_result.verification.occurred is True
        assert eval_result.verification.passed is True
        assert eval_result.verification.summary == "Verification passed"

        # Public projection is strictly {}
        pub_result = run_antigravity_post_tool_use(json.dumps(payload))
        assert pub_result == {}


def test_post_tool_use_opt_in_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid write + opt-in -> verifier fails -> verification_failed."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "replace_file_content",
            "args": {"TargetFile": "src/lib.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    mock_verif = {
        "passed": False,
        "checks": [
            {
                "name": "lint",
                "passed": False,
                "output": "line too long",
                "duration_sec": 0.1,
            }
        ],
        "summary": "Failed 1/1 verification checks: lint.",
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ):
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert eval_result.disposition == "continue"
        assert eval_result.reason_code == "verification_failed"
        assert eval_result.verification is not None
        assert eval_result.verification.occurred is True
        assert eval_result.verification.passed is False
        assert eval_result.verification.summary == "Verification failed"

        pub_result = run_antigravity_post_tool_use(json.dumps(payload))
        assert pub_result == {}


def test_post_tool_use_no_executable_checks_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No executable checks detected is treated as verification failure."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "readme.txt"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    mock_verif = {
        "passed": False,
        "checks": [],
        "summary": "No executable verification checks were detected.",
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ):
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert eval_result.disposition == "continue"
        assert eval_result.reason_code == "verification_failed"
        assert eval_result.verification is not None
        assert eval_result.verification.occurred is True
        assert eval_result.verification.passed is False
        assert (
            eval_result.verification.summary
            == "No executable checks detected"
        )


@pytest.mark.parametrize(
    "env_val",
    [None, "", "0", "true", "yes", "2", " 1 ", "1\n"],
)
def test_post_tool_use_disabled_env_never_calls_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_val: str | None
) -> None:
    """Non-'1' env values never invoke verifier; result is not_applicable."""
    if env_val is None:
        monkeypatch.delenv(POST_ACTION_VERIFY_ENV, raising=False)
    else:
        monkeypatch.setenv(POST_ACTION_VERIFY_ENV, env_val)

    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify"
    ) as mock_rv:
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        mock_rv.assert_not_called()
        assert eval_result.disposition == "continue"
        assert eval_result.reason_code == "not_applicable"
        assert eval_result.verification is not None
        assert eval_result.verification.occurred is False
        assert eval_result.verification.passed is None

        assert run_antigravity_post_tool_use(json.dumps(payload)) == {}


def test_payload_cannot_enable_or_configure_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Payload attempting to configure or force verification is ignored."""
    monkeypatch.delenv(POST_ACTION_VERIFY_ENV, raising=False)
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
        "MIGHTY_MOUSE_POST_ACTION_VERIFY": "1",
        "verify": True,
        "test_command": "rm -rf /",
        "timeout_sec": 1,
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify"
    ) as mock_rv:
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        mock_rv.assert_not_called()
        assert eval_result.reason_code == "not_applicable"
        assert eval_result.verification is not None
        assert eval_result.verification.occurred is False


def test_shell_command_post_tool_use_never_triggers_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_command PostToolUse is not a write and never triggers verifier."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "echo hello"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify"
    ) as mock_rv:
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        mock_rv.assert_not_called()
        assert eval_result.disposition == "continue"
        assert eval_result.reason_code == "not_applicable"
        assert eval_result.verification is not None
        assert eval_result.verification.occurred is False


def test_other_tool_post_tool_use_never_triggers_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other non-write tool PostToolUse never triggers verifier."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "read_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify"
    ) as mock_rv:
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        mock_rv.assert_not_called()
        assert eval_result.reason_code == "not_applicable"


def test_malformed_json_returns_empty_dict_and_no_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed JSON input fails closed without calling verifier."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify"
    ) as mock_rv:
        eval_result = evaluate_antigravity_post_tool_use('{"bad": json')
        mock_rv.assert_not_called()
        assert eval_result.disposition == "deny"
        assert eval_result.reason_code == "malformed_event"

        assert run_antigravity_post_tool_use('{"bad": json') == {}


@pytest.mark.parametrize(
    "non_obj",
    ["[]", '"str"', "42", "true", "null"],
)
def test_non_object_json_returns_empty_dict(
    monkeypatch: pytest.MonkeyPatch, non_obj: str
) -> None:
    """Non-object JSON root returns empty dict."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    eval_result = evaluate_antigravity_post_tool_use(non_obj)
    assert eval_result.disposition == "deny"
    assert eval_result.reason_code == "malformed_event"
    assert run_antigravity_post_tool_use(non_obj) == {}


def test_missing_runtime_context_no_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing adapter config denies and never invokes verifier."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    # tmp_path has no config
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify"
    ) as mock_rv:
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        mock_rv.assert_not_called()
        assert eval_result.disposition == "deny"
        assert eval_result.reason_code == "runtime_context_unavailable"

        assert run_antigravity_post_tool_use(json.dumps(payload)) == {}


def test_canonical_resolved_event_formed_before_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ResolvedHostHookEvent is constructed prior to verifier call."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    resolved_order: list[str] = []

    orig_init = ResolvedHostHookEvent.__init__

    def tracking_init(self: Any, *args: Any, **kwargs: Any) -> None:
        orig_init(self, *args, **kwargs)
        resolved_order.append("resolved_event")

    def mock_run_verify(ws: str) -> dict[str, Any]:
        resolved_order.append("run_verify")
        return {"passed": True, "checks": [{"name": "t", "passed": True}]}

    with patch.object(
        ResolvedHostHookEvent, "__init__", tracking_init
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=mock_run_verify,
    ):
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert eval_result.reason_code == "verification_passed"
        assert resolved_order == ["resolved_event", "run_verify"]


def test_exact_mcp_v6_signatures_supplied(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exact MCP v6 / 15 tool signatures are supplied to resolver."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    sigs = _get_mcp_tool_signatures()
    assert len(sigs) == 15

    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch.object(
        HostAdapter,
        "resolve_adapter_context",
        wraps=HostAdapter.resolve_adapter_context,
    ) as mock_resolve, patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value={"passed": True, "checks": []},
    ):
        evaluate_antigravity_post_tool_use(json.dumps(payload))
        mock_resolve.assert_called_once()
        _, kwargs = mock_resolve.call_args
        assert kwargs["contract_version"] == 6
        assert set(kwargs["tool_signatures"].keys()) == set(sigs.keys())


def test_privacy_no_verifier_output_or_secrets_leakage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifier command lines, secret paths, outputs, and errors never leak."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    secret_path = str(tmp_path / "secret" / "token.txt")
    secret_cmd = "cat /etc/shadow"
    secret_output = "LEAKED_INTERNAL_SECRET_PASSWORD_12345"

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": secret_path},
        },
        "workspacePaths": [str(tmp_path)],
        "error": "HOST_ERROR_SECRET_CONTENT_999",
    }

    mock_verif = {
        "passed": False,
        "checks": [
            {
                "name": "tests",
                "passed": False,
                "output": f"Error running {secret_cmd}: {secret_output}",
                "duration_sec": 1.2,
            }
        ],
        "summary": f"Failed test at {secret_path}",
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ):
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        # Ensure summary on verification is strictly bounded
        assert eval_result.verification is not None
        assert eval_result.verification.summary == "Verification failed"
        assert secret_output not in str(eval_result)
        assert secret_cmd not in str(eval_result)
        assert "HOST_ERROR_SECRET_CONTENT" not in str(eval_result)

        # Public output is strictly {}
        pub = run_antigravity_post_tool_use(json.dumps(payload))
        assert pub == {}
        assert json.dumps(pub) == "{}"


def test_stdout_parses_as_exactly_empty_json_object(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """post_tool_use_main() outputs exactly '{}' followed by newline."""
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    post_tool_use_main()
    captured = capsys.readouterr()
    assert captured.err == ""
    assert captured.out == "{}\n"
    assert json.loads(captured.out.strip()) == {}


def test_no_mutating_or_solving_methods_invoked(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runner never calls solve, solve_swarm, record_signal, or policies."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch.object(
        HostAdapter, "solve", side_effect=AssertionError("solve called")
    ), patch.object(
        HostAdapter,
        "solve_swarm",
        side_effect=AssertionError("solve_swarm called"),
    ), patch.object(
        HostAdapter,
        "record_signal",
        side_effect=AssertionError("record_signal called"),
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value={
            "passed": True,
            "checks": [{"name": "t", "passed": True}],
        },
    ):
        res = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert res.reason_code == "verification_passed"


def test_workspace_files_untouched_by_runner_logic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runner logic does not mutate workspace files."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    test_file = tmp_path / "important.txt"
    test_file.write_text("pre-existing content\n", encoding="utf-8")
    before_mtime = test_file.stat().st_mtime_ns

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "important.txt"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value={"passed": True, "checks": []},
    ):
        run_antigravity_post_tool_use(json.dumps(payload))
        assert test_file.read_text(encoding="utf-8") == (
            "pre-existing content\n"
        )
        assert test_file.stat().st_mtime_ns == before_mtime


def test_cli_subprocess_post_tool_use_invocation(tmp_path: Path) -> None:
    """Direct subprocess invocation of mighty-mouse-antigravity-posttooluse."""
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/lib.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    cmd = [
        sys.executable,
        "-W",
        "ignore",
        "-c",
        "from mighty_mouse_mcp.antigravity_hooks import post_tool_use_main; "
        "post_tool_use_main()",
    ]
    env = {
        "PYTHONPATH": "src:mcp/src",
        "PATH": "/bin:/usr/bin",
    }
    proc = subprocess.run(
        cmd,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
        env=env,
    )
    assert proc.returncode == 0
    assert proc.stderr == ""
    assert proc.stdout == "{}\n"
    assert json.loads(proc.stdout.strip()) == {}
