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
    HookRecoverySummary,
    HostHookResult,
    ResolvedHostHookEvent,
)
from mighty_mouse.host.recovery_execution import (
    RecoveryExecutionAttempt,
    RecoveryExecutionRequest,
)
from mighty_mouse.v2.signals import SignalLifecycle
from mighty_mouse_mcp.antigravity_hooks import (
    POST_ACTION_RECOVERY_CONFIG_ENV,
    POST_ACTION_RECOVERY_ENV,
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
    """Valid write + opt-in -> verifier called once, passes, records Signal."""
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

        # Signal receipt must be recorded in state_dir
        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        receipts = list(receipt_dir.glob("*.json"))
        assert len(receipts) == 1
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        sig = receipt["signal"]
        assert sig["outcome"] == "passed"
        assert sig["verifier_category"] == "tests"
        assert sig["verifier_result"] == "passed"
        assert sig["duration_ms"] == 500
        assert sig["retry_count"] == 0
        assert sig["scope"]["repository"] == "JOHNNYMACONNY/mighty-mouse"
        assert sig["scope"]["model_class"] == "local-small"
        assert sig["scope"]["mode"] == "coding"
        assert sig["scope"]["task_category"] == "unknown"

        # Public projection is strictly {}
        pub_result = run_antigravity_post_tool_use(json.dumps(payload))
        assert pub_result == {}


def test_post_tool_use_opt_in_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Valid write + opt-in -> verifier fails -> records failed Signal."""
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

        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        receipts = list(receipt_dir.glob("*.json"))
        assert len(receipts) == 1
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        sig = receipt["signal"]
        assert sig["outcome"] == "failed"
        assert sig["verifier_category"] == "lint"
        assert sig["verifier_result"] == "failed"
        assert sig["duration_ms"] == 100

        pub_result = run_antigravity_post_tool_use(json.dumps(payload))
        assert pub_result == {}


def test_post_tool_use_no_executable_checks_detected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """No checks detected is treated as failed verification Signal."""
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

        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        receipts = list(receipt_dir.glob("*.json"))
        assert len(receipts) == 1
        receipt = json.loads(receipts[0].read_text(encoding="utf-8"))
        sig = receipt["signal"]
        assert sig["outcome"] == "failed"
        assert sig["verifier_category"] == "none"
        assert sig["verifier_result"] == "failed"


@pytest.mark.parametrize(
    "env_val",
    [None, "", "0", "true", "yes", "2", " 1 ", "1\n"],
)
def test_post_tool_use_disabled_env_never_calls_verifier(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_val: str | None
) -> None:
    """Non-'1' env values never invoke verifier and record NO Signal."""
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

        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        assert (
            not receipt_dir.exists()
            or len(list(receipt_dir.glob("*.json"))) == 0
        )

        assert run_antigravity_post_tool_use(json.dumps(payload)) == {}


def test_payload_cannot_enable_or_configure_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Payload attempting to configure verifier is ignored; no Signal."""
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

        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        assert (
            not receipt_dir.exists()
            or len(list(receipt_dir.glob("*.json"))) == 0
        )


def test_shell_command_post_tool_use_never_triggers_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """run_command PostToolUse never triggers verifier / no Signal."""
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

        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        assert (
            not receipt_dir.exists()
            or len(list(receipt_dir.glob("*.json"))) == 0
        )


def test_other_tool_post_tool_use_never_triggers_verification(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Other non-write tool PostToolUse never triggers verifier / no Signal."""
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

        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        assert (
            not receipt_dir.exists()
            or len(list(receipt_dir.glob("*.json"))) == 0
        )


def test_malformed_json_returns_empty_dict_and_no_verifier(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Malformed JSON input fails closed without calling verifier or Signal."""
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
    """Missing adapter config denies, never invokes verifier or Signal."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
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
    """Verifier command lines and outputs never leak into Signal or result."""
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
        assert eval_result.verification is not None
        assert eval_result.verification.summary == "Verification failed"
        assert secret_output not in str(eval_result)
        assert secret_cmd not in str(eval_result)
        assert "HOST_ERROR_SECRET_CONTENT" not in str(eval_result)

        # Inspect persisted Signal file
        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        receipts = list(receipt_dir.glob("*.json"))
        assert len(receipts) == 1
        raw_receipt = receipts[0].read_text(encoding="utf-8")
        assert secret_output not in raw_receipt
        assert secret_cmd not in raw_receipt
        assert "HOST_ERROR_SECRET_CONTENT" not in raw_receipt
        assert secret_path not in raw_receipt

        # Public output is strictly {}
        pub = run_antigravity_post_tool_use(json.dumps(payload))
        assert pub == {}
        assert json.dumps(pub) == "{}"


def test_paused_signal_collection_is_non_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When Signal collection is paused, verification completes normally."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    lifecycle = SignalLifecycle(tmp_path / ".mighty-mouse")
    lifecycle.pause()
    assert lifecycle.collection_paused is True

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    mock_verif = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.2}],
        "summary": "Passed 1/1 verification checks.",
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ):
        eval_result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert eval_result.disposition == "continue"
        assert eval_result.reason_code == "verification_passed"
        assert eval_result.verification is not None
        assert eval_result.verification.passed is True

        # No receipt written because paused
        receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
        assert (
            not receipt_dir.exists()
            or len(list(receipt_dir.glob("*.json"))) == 0
        )

        assert run_antigravity_post_tool_use(json.dumps(payload)) == {}


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
    """Runner never calls solve, solve_swarm, or policy engine controls."""
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


def test_failed_verification_with_recovery_env_invokes_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed verification + recovery env 1 calls gate with enabled=True."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    mock_verif = {
        "passed": False,
        "checks": [
            {
                "name": "tests",
                "passed": False,
                "output": "1 failed",
                "duration_sec": 0.2,
            }
        ],
        "summary": "Failed 1/1 verification checks.",
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate",
    ) as mock_gate:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))

        assert mock_gate.call_count == 1
        args, kwargs = mock_gate.call_args
        assert isinstance(args[0], ResolvedHostHookEvent)
        assert args[1].occurred is True
        assert args[1].passed is False
        assert kwargs == {
            "enabled": True,
            "attempts_used": 0,
            "recovery_in_progress": False,
        }

        assert result.disposition == "continue"
        assert result.reason_code == "verification_failed"
        assert result.recovery is None


@pytest.mark.parametrize("env_val", [None, "0", "true", "TRUE", "yes", "2"])
def test_failed_verification_with_disabled_or_invalid_env_calls_gate_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_val: str | None
) -> None:
    """Failed verification + env absent/non-1 calls gate with enabled=False."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    if env_val is None:
        monkeypatch.delenv(POST_ACTION_RECOVERY_ENV, raising=False)
    else:
        monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, env_val)

    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    mock_verif = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate",
    ) as mock_gate:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_gate.call_count == 1
        _, kwargs = mock_gate.call_args
        assert kwargs["enabled"] is False
        assert result.recovery is None


def test_passed_verification_passes_to_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passed verification calls gate and returns verification_passed."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    mock_verif = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.1}],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate",
    ) as mock_gate:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_gate.call_count == 1
        args, _ = mock_gate.call_args
        assert args[1].passed is True
        assert result.reason_code == "verification_passed"
        assert result.recovery is None


def test_verification_disabled_does_not_invoke_recovery_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When verification is disabled, recovery gate is never called."""
    monkeypatch.delenv(POST_ACTION_VERIFY_ENV, raising=False)
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate"
    ) as mock_gate:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_gate.call_count == 0
        assert result.reason_code == "not_applicable"
        assert result.recovery is None


def test_non_write_action_does_not_invoke_recovery_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-write action (e.g. read_file) does not invoke recovery gate."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "read_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate"
    ) as mock_gate:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_gate.call_count == 0
        assert result.reason_code == "not_applicable"


def test_malformed_payload_does_not_invoke_recovery_gate() -> None:
    """Malformed payload fails closed without invoking recovery gate."""
    with patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate"
    ) as mock_gate:
        result = evaluate_antigravity_post_tool_use("invalid json{")
        assert mock_gate.call_count == 0
        assert result.disposition == "deny"


def test_verifier_exception_does_not_invoke_recovery_gate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Verifier exception returns internal_error without invoking gate."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=RuntimeError("verifier crashed"),
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate"
    ) as mock_gate:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_gate.call_count == 0
        assert result.reason_code == "internal_error"


def test_recovery_gate_exception_is_non_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If evaluate_recovery_gate raises, PostToolUse continues normally."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    mock_verif = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate",
        side_effect=RuntimeError("gate exception"),
    ):
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert result.disposition == "continue"
        assert result.reason_code == "verification_failed"
        assert result.recovery is None

        rendered = run_antigravity_post_tool_use(json.dumps(payload))
        assert rendered == {}


def test_payload_recovery_spoofing_has_no_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Payload attempting to inject recovery controls has zero authority."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.delenv(POST_ACTION_RECOVERY_ENV, raising=False)
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/app.py",
                "recovery_enabled": True,
                "attempts_used": 0,
                "recovery_in_progress": False,
            },
        },
        "workspacePaths": [str(tmp_path)],
        "recovery": {"enabled": True},
    }
    mock_verif = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.evaluate_recovery_gate",
    ) as mock_gate:
        evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_gate.call_count == 1
        _, kwargs = mock_gate.call_args
        assert kwargs["enabled"] is False


def _setup_recovery_config_file(tmp_path: Path) -> Path:
    """Create a minimal valid recovery model config file."""
    cfg_file = tmp_path / "recovery_model_config.yaml"
    cfg_file.write_text(
        "model: test-model\n"
        "temperature: 0.0\n"
        "provider: sim\n"
        "allow_simulation: true\n",
        encoding="utf-8",
    )
    return cfg_file


def test_recovery_verification_passed_zero_recovery_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passed verification results in zero recovery execution calls."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    mock_verif = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.1}],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
    ) as mock_exec:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_exec.call_count == 0
        assert result.reason_code == "verification_passed"
        assert result.verification is not None
        assert result.verification.passed is True
        assert result.recovery is None


def test_recovery_disabled_zero_recovery_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed verification with recovery disabled executes zero attempts."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.delenv(POST_ACTION_RECOVERY_ENV, raising=False)
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    mock_verif = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
    ) as mock_exec:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_exec.call_count == 0
        assert result.reason_code == "verification_failed"
        assert result.recovery is None


@pytest.mark.parametrize(
    "cfg_env",
    [None, "", "nonexistent_config_file.yaml"],
)
def test_recovery_config_absent_or_invalid_bounded_no_solver(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cfg_env: str | None
) -> None:
    """Missing or invalid recovery config produces bounded non-attempt."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    if cfg_env is None:
        monkeypatch.delenv(POST_ACTION_RECOVERY_CONFIG_ENV, raising=False)
    elif cfg_env == "":
        monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, "")
    else:
        monkeypatch.setenv(
            POST_ACTION_RECOVERY_CONFIG_ENV, str(tmp_path / cfg_env)
        )

    _setup_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }
    mock_verif = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=mock_verif,
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
    ) as mock_exec:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_exec.call_count == 0
        assert result.reason_code == "verification_failed"
        assert result.recovery is None
        rendered = run_antigravity_post_tool_use(json.dumps(payload))
        assert rendered == {}


def test_recovery_success_flow_solver_complete_reverify_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Successful recovery: solver completed and re-verification passed."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }
    verif_pass = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.2}],
    }

    mock_attempt = RecoveryExecutionAttempt(
        attempted=True,
        completed=True,
        attempts=1,
        execution_mode="agent",
        output_paths=("src/app.py",),
    )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_pass],
    ) as mock_verif, patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        return_value=mock_attempt,
    ) as mock_exec:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_exec.call_count == 1
        assert mock_verif.call_count == 2
        assert result.disposition == "continue"
        assert result.reason_code == "recovery_succeeded"
        assert result.summary == "Recovery succeeded"
        assert result.verification is not None
        assert result.verification.passed is True
        assert result.recovery == HookRecoverySummary(
            attempted=True,
            succeeded=True,
            attempts=1,
            execution_mode="agent",
        )

        rendered = run_antigravity_post_tool_use(json.dumps(payload))
        assert rendered == {}

    receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
    receipts = list(receipt_dir.glob("*.json"))
    assert len(receipts) == 2
    sigs = [
        json.loads(p.read_text(encoding="utf-8"))["signal"]
        for p in receipts
    ]
    sigs.sort(key=lambda s: s["retry_count"])
    assert sigs[0]["retry_count"] == 0
    assert sigs[0]["outcome"] == "failed"
    assert sigs[1]["retry_count"] == 1
    assert sigs[1]["outcome"] == "passed"


def test_recovery_failure_flow_solver_complete_reverify_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failed recovery: solver completed but re-verification failed."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    mock_attempt = RecoveryExecutionAttempt(
        attempted=True,
        completed=True,
        attempts=1,
        execution_mode="agent",
        output_paths=("src/app.py",),
    )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_fail],
    ) as mock_verif, patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        return_value=mock_attempt,
    ) as mock_exec:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_exec.call_count == 1
        assert mock_verif.call_count == 2
        assert result.reason_code == "recovery_failed"
        assert result.summary == "Recovery failed"
        assert result.verification is not None
        assert result.verification.passed is False
        assert result.recovery == HookRecoverySummary(
            attempted=True,
            succeeded=False,
            attempts=1,
            execution_mode="agent",
        )

    receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
    receipts = list(receipt_dir.glob("*.json"))
    assert len(receipts) == 2
    sigs = [
        json.loads(p.read_text(encoding="utf-8"))["signal"]
        for p in receipts
    ]
    sigs.sort(key=lambda s: s["retry_count"])
    assert sigs[0]["retry_count"] == 0
    assert sigs[0]["outcome"] == "failed"
    assert sigs[1]["retry_count"] == 1
    assert sigs[1]["outcome"] == "failed"


def test_recovery_success_flow_solver_incomplete_reverify_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Solver incomplete, but re-verify passed -> recovery_succeeded."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }
    verif_pass = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.1}],
    }

    mock_attempt = RecoveryExecutionAttempt(
        attempted=True,
        completed=False,
        attempts=1,
        execution_mode="agent",
        output_paths=(),
        error_summary="Timeout during solver response",
    )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_pass],
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        return_value=mock_attempt,
    ):
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert result.reason_code == "recovery_succeeded"
        assert result.recovery is not None
        assert result.recovery.succeeded is True


def test_recovery_failure_flow_solver_incomplete_reverify_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Solver incomplete and re-verification failed -> recovery_failed."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    mock_attempt = RecoveryExecutionAttempt(
        attempted=True,
        completed=False,
        attempts=1,
        execution_mode="agent",
        output_paths=(),
        error_summary="Solver error",
    )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_fail],
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        return_value=mock_attempt,
    ):
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert result.reason_code == "recovery_failed"
        assert result.recovery is not None
        assert result.recovery.succeeded is False


def test_recovery_attempt_receives_canonical_target_paths_and_trusted_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery execution receives canonical target paths and trusted task."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/module/service.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }
    verif_pass = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.1}],
    }

    captured_request: list[RecoveryExecutionRequest] = []
    captured_task_content: list[dict[str, Any]] = []
    task_path_holder: list[str] = []

    def mock_exec_fn(
        req: RecoveryExecutionRequest,
    ) -> RecoveryExecutionAttempt:
        captured_request.append(req)
        task_path_holder.append(req.task_input_path)
        with open(req.task_input_path, "r", encoding="utf-8") as f:
            captured_task_content.append(json.load(f))
        return RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=1,
            execution_mode="agent",
            output_paths=("src/module/service.py",),
        )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_pass],
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        side_effect=mock_exec_fn,
    ):
        evaluate_antigravity_post_tool_use(json.dumps(payload))

    assert len(captured_request) == 1
    req = captured_request[0]
    assert req.resolved_event.event.action.target_paths == (
        "src/module/service.py",
    )
    assert req.p_cfg_path == str(cfg_file)
    assert req.decision.eligible is True
    assert req.decision.execution_mode == "agent"

    assert len(captured_task_content) == 1
    task_data = captured_task_content[0]
    assert task_data["expected_files"] == ["src/module/service.py"]
    assert "src/module/service.py" in task_data["instruction"]
    assert "Deletions are prohibited" in task_data["instruction"]

    # Verify task file is removed after execution
    assert not Path(task_path_holder[0]).exists()


def test_recovery_hostile_host_payload_fields_do_not_leak_into_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Hostile host fields never leak into recovery task or authority."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/safe.py",
                "malicious_command": "rm -rf /",
            },
        },
        "workspacePaths": [str(tmp_path)],
        "error": "HOSTILE_ERROR_PAYLOAD",
        "modelName": "HOSTILE_MODEL",
        "transcriptPath": "/tmp/hostile_transcript",
        "conversationId": "evil-conversation-99",
        "stepIdx": 1337,
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }
    verif_pass = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.1}],
    }

    captured_task_str: list[str] = []

    def mock_exec_fn(
        req: RecoveryExecutionRequest,
    ) -> RecoveryExecutionAttempt:
        with open(req.task_input_path, "r", encoding="utf-8") as f:
            captured_task_str.append(f.read())
        return RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=1,
            execution_mode="agent",
        )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_pass],
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        side_effect=mock_exec_fn,
    ):
        evaluate_antigravity_post_tool_use(json.dumps(payload))

    assert len(captured_task_str) == 1
    raw = captured_task_str[0]
    assert "HOSTILE_ERROR_PAYLOAD" not in raw
    assert "HOSTILE_MODEL" not in raw
    assert "hostile_transcript" not in raw
    assert "evil-conversation-99" not in raw
    assert "1337" not in raw
    assert "rm -rf" not in raw


def test_recovery_non_attempt_does_not_reverify_or_record_signal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Non-attempted recovery returns bounded failure without re-verify."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    mock_attempt = RecoveryExecutionAttempt(
        attempted=False,
        completed=False,
        attempts=0,
        execution_mode=None,
        error_summary="Gate disqualified attempt",
    )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        return_value=verif_fail,
    ) as mock_verif, patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        return_value=mock_attempt,
    ) as mock_exec:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert mock_exec.call_count == 1
        # Exactly one verification call (initial), NOT re-verify
        assert mock_verif.call_count == 1
        assert result.reason_code == "verification_failed"
        assert result.recovery is None

    receipt_dir = tmp_path / ".mighty-mouse" / "v2-signal-receipts"
    receipts = list(receipt_dir.glob("*.json"))
    assert len(receipts) == 1
    sig = json.loads(receipts[0].read_text(encoding="utf-8"))["signal"]
    assert sig["retry_count"] == 0


def test_recovery_reverification_exception_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Re-verification exception results in bounded recovery_failed."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }

    mock_attempt = RecoveryExecutionAttempt(
        attempted=True,
        completed=True,
        attempts=1,
        execution_mode="agent",
    )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, RuntimeError("disk corrupt during reverify")],
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        return_value=mock_attempt,
    ):
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert result.reason_code == "recovery_failed"
        assert result.verification is not None
        assert result.verification.passed is False
        assert result.recovery is not None
        assert result.recovery.succeeded is False

        rendered = run_antigravity_post_tool_use(json.dumps(payload))
        assert rendered == {}


def test_recovery_signal_recording_failure_is_non_fatal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Failure in telemetry recording does not alter recovery outcome."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }
    verif_pass = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.1}],
    }

    mock_attempt = RecoveryExecutionAttempt(
        attempted=True,
        completed=True,
        attempts=1,
        execution_mode="agent",
    )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_pass],
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        return_value=mock_attempt,
    ), patch(
        "mighty_mouse.v2.telemetry.SignalTelemetry.record",
        side_effect=RuntimeError("telemetry storage full"),
    ):
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert result.reason_code == "recovery_succeeded"
        assert result.recovery is not None
        assert result.recovery.succeeded is True


def test_recovery_does_not_dispatch_antigravity_tools(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Recovery execution relies on internal response application.

    Proves no recursive Antigravity tool dispatch occurs.
    """
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }
    verif_pass = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.1}],
    }

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_pass],
    ), patch(
        "mighty_mouse.orchestrator.mighty_mouse_agent."
        "_solve_with_runtime_context",
        return_value=("src/app.py",),
    ) as mock_agent_solve, patch(
        "mighty_mouse_mcp.antigravity_hooks.run_antigravity_pre_tool_use",
    ) as mock_pre_hook:
        result = evaluate_antigravity_post_tool_use(json.dumps(payload))
        assert result.reason_code == "recovery_succeeded"
        assert mock_agent_solve.call_count == 1
        # No recursive Antigravity tool calls were triggered
        assert mock_pre_hook.call_count == 0


def test_recovery_cli_post_tool_use_main_outputs_empty_dict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """CLI post_tool_use_main outputs strictly '{}' on recovery path."""
    monkeypatch.setenv(POST_ACTION_VERIFY_ENV, "1")
    monkeypatch.setenv(POST_ACTION_RECOVERY_ENV, "1")
    cfg_file = _setup_recovery_config_file(tmp_path)
    monkeypatch.setenv(POST_ACTION_RECOVERY_CONFIG_ENV, str(cfg_file))
    _setup_workspace_adapter_config(tmp_path)

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/app.py"},
        },
        "workspacePaths": [str(tmp_path)],
    }

    verif_fail = {
        "passed": False,
        "checks": [{"name": "tests", "passed": False, "duration_sec": 0.1}],
    }
    verif_pass = {
        "passed": True,
        "checks": [{"name": "tests", "passed": True, "duration_sec": 0.1}],
    }

    mock_attempt = RecoveryExecutionAttempt(
        attempted=True,
        completed=True,
        attempts=1,
        execution_mode="agent",
    )

    with patch(
        "mighty_mouse_mcp.antigravity_hooks.run_verify",
        side_effect=[verif_fail, verif_pass],
    ), patch(
        "mighty_mouse_mcp.antigravity_hooks.execute_recovery_attempt",
        return_value=mock_attempt,
    ), patch("sys.stdin", io.StringIO(json.dumps(payload))):
        post_tool_use_main()

    captured = capsys.readouterr()
    assert captured.out == "{}\n"
    assert captured.err == ""
