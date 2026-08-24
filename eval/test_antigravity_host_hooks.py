"""Tests for Antigravity PreToolUse host hook leaf adapter v1."""

from __future__ import annotations

import pytest

from mighty_mouse.host.antigravity import (
    adapt_antigravity_pre_tool_use,
    render_antigravity_pre_tool_use_result,
)
from mighty_mouse.host.hooks import HostHookEvent, HostHookResult


def test_valid_tool_mappings() -> None:
    """Supported tools map to exact expected kind and mutation_class."""
    # write_to_file
    p1 = {
        "tool_name": "write_to_file",
        "workspace_path": "/path/to/ws",
        "tool_input": {"TargetFile": "src/module.py", "CodeContent": "pass"},
        "conversation_id": "conv-1",
    }
    e1 = adapt_antigravity_pre_tool_use(p1, event_id="evt-1")
    assert isinstance(e1, HostHookEvent)
    assert e1.schema_version == 1
    assert e1.phase == "pre_action"
    assert e1.source == "antigravity"
    assert e1.workspace == "/path/to/ws"
    assert e1.session_id == "conv-1"
    assert e1.action.kind == "file_write"
    assert e1.action.mutation_class == "workspace_mutation"
    assert e1.action.target_paths == ("src/module.py",)

    # replace_file_content
    p2 = {
        "tool_name": "replace_file_content",
        "workspace_path": "/path/to/ws",
        "tool_input": {"file_path": "eval/test_x.py"},
    }
    e2 = adapt_antigravity_pre_tool_use(p2, event_id="evt-2")
    assert isinstance(e2, HostHookEvent)
    assert e2.action.kind == "file_write"
    assert e2.action.mutation_class == "workspace_mutation"
    assert e2.action.target_paths == ("eval/test_x.py",)

    # multi_replace_file_content with TargetFile
    p3 = {
        "tool_name": "multi_replace_file_content",
        "workspace_path": "/path/to/ws",
        "tool_input": {"TargetFile": "docs/readme.md"},
    }
    e3 = adapt_antigravity_pre_tool_use(p3, event_id="evt-3")
    assert isinstance(e3, HostHookEvent)
    assert e3.action.kind == "file_write"
    assert e3.action.mutation_class == "workspace_mutation"
    assert e3.action.target_paths == ("docs/readme.md",)

    # run_command (command text never carried into event)
    p4 = {
        "tool_name": "run_command",
        "workspace_path": "/path/to/ws",
        "tool_input": {
            "CommandLine": "rm -rf /tmp/secret",
            "Cwd": "/path/to/ws",
        },
    }
    e4 = adapt_antigravity_pre_tool_use(p4, event_id="evt-4")
    assert isinstance(e4, HostHookEvent)
    assert e4.action.kind == "shell_command"
    assert e4.action.mutation_class == "unknown"
    assert e4.action.target_paths == ()
    # Ensure command text does not appear anywhere in event dataclass fields
    assert "rm -rf" not in str(e4)


def test_target_file_aliases_and_contradiction() -> None:
    """TargetFile and file_path resolution handles matching/contradiction."""
    # Both present and equal -> accepted once
    p_eq = {
        "tool_name": "write_to_file",
        "workspace_path": "/ws",
        "tool_input": {"TargetFile": "src/a.py", "file_path": "src/a.py"},
    }
    e_eq = adapt_antigravity_pre_tool_use(p_eq, event_id="evt-eq")
    assert isinstance(e_eq, HostHookEvent)
    assert e_eq.action.target_paths == ("src/a.py",)

    # Cross-platform equivalent paths (Windows backslash vs POSIX slash)
    p_win_posix = {
        "tool_name": "write_to_file",
        "workspace_path": "/ws",
        "tool_input": {
            "TargetFile": r"src\pkg\a.py",
            "file_path": "src/pkg/a.py",
        },
    }
    e_win_posix = adapt_antigravity_pre_tool_use(
        p_win_posix, event_id="evt-win-posix"
    )
    assert isinstance(e_win_posix, HostHookEvent)
    assert e_win_posix.action.target_paths == ("src/pkg/a.py",)

    # Relative dot prefix normalization -> accepted once
    p_dot = {
        "tool_name": "write_to_file",
        "workspace_path": "/ws",
        "tool_input": {
            "TargetFile": "./src/a.py",
            "file_path": "src/a.py",
        },
    }
    e_dot = adapt_antigravity_pre_tool_use(p_dot, event_id="evt-dot")
    assert isinstance(e_dot, HostHookEvent)
    assert e_dot.action.target_paths == ("src/a.py",)

    # Contradictory target paths -> deny
    p_diff = {
        "tool_name": "write_to_file",
        "workspace_path": "/ws",
        "tool_input": {"TargetFile": "src/a.py", "file_path": "src/b.py"},
    }
    r_diff = adapt_antigravity_pre_tool_use(p_diff, event_id="evt-diff")
    assert isinstance(r_diff, HostHookResult)
    assert r_diff.disposition == "deny"
    assert r_diff.reason_code == "malformed_event"

    # Explicit None or whitespace target -> deny
    for bad_val in (None, "   ", 123, []):
        r_bad = adapt_antigravity_pre_tool_use(
            {
                "tool_name": "write_to_file",
                "workspace_path": "/ws",
                "tool_input": {"TargetFile": bad_val},
            },
            event_id="evt-bad-val",
        )
        assert isinstance(r_bad, HostHookResult)
        assert r_bad.disposition == "deny"

    # Unsupported 'path' alias ignored -> target_paths becomes empty tuple
    p_path = {
        "tool_name": "write_to_file",
        "workspace_path": "/ws",
        "tool_input": {"path": "src/a.py"},
    }
    e_path = adapt_antigravity_pre_tool_use(p_path, event_id="evt-path")
    assert isinstance(e_path, HostHookEvent)
    assert e_path.action.target_paths == ()


def test_alias_resolution_and_conflict_handling() -> None:
    """Aliases resolve properly; conflicting/malformed aliases fail closed."""
    # Tool aliases
    for key in ("tool_name", "tool", "name", "tool_call"):
        res = adapt_antigravity_pre_tool_use(
            {key: "run_command", "workspace": "/ws"},
            event_id="evt-alias",
        )
        assert isinstance(res, HostHookEvent)

    # Workspace aliases
    for key in ("workspace_path", "workspace", "cwd"):
        res = adapt_antigravity_pre_tool_use(
            {"tool": "run_command", key: "/my/ws"},
            event_id="evt-ws",
        )
        assert isinstance(res, HostHookEvent)
        assert res.workspace == "/my/ws"

    # Session ID aliases
    for key in ("conversation_id", "conversationId", "session_id"):
        res = adapt_antigravity_pre_tool_use(
            {"tool": "run_command", "cwd": "/my/ws", key: "sess-99"},
            event_id="evt-sess",
        )
        assert isinstance(res, HostHookEvent)
        assert res.session_id == "sess-99"

    # Absent session_id -> None session_id in event
    res_no_sess = adapt_antigravity_pre_tool_use(
        {"tool": "run_command", "cwd": "/my/ws"},
        event_id="evt-no-sess",
    )
    assert isinstance(res_no_sess, HostHookEvent)
    assert res_no_sess.session_id is None

    # Present None required aliases fail closed
    assert adapt_antigravity_pre_tool_use(
        {"tool_name": None, "tool": "run_command", "workspace": "/ws"},
        event_id="e",
    ).disposition == "deny"

    assert adapt_antigravity_pre_tool_use(
        {"workspace_path": None, "cwd": "/ws", "tool": "run_command"},
        event_id="e",
    ).disposition == "deny"

    assert adapt_antigravity_pre_tool_use(
        {"tool_input": None, "workspace": "/ws", "tool": "run_command"},
        event_id="e",
    ).disposition == "deny"

    assert adapt_antigravity_pre_tool_use(
        {
            "tool_input": None,
            "args": {},
            "workspace": "/ws",
            "tool": "run_command",
        },
        event_id="e",
    ).disposition == "deny"

    # Conflicting tool names -> fail closed
    res_conflict_tool = adapt_antigravity_pre_tool_use(
        {
            "tool_name": "write_to_file",
            "tool": "run_command",
            "workspace": "/ws",
        },
        event_id="evt-conflict-tool",
    )
    assert isinstance(res_conflict_tool, HostHookResult)
    assert res_conflict_tool.disposition == "deny"
    assert res_conflict_tool.reason_code == "malformed_event"

    # Conflicting workspaces -> fail closed
    res_conflict_ws = adapt_antigravity_pre_tool_use(
        {
            "tool_name": "run_command",
            "workspace_path": "/ws1",
            "cwd": "/ws2",
        },
        event_id="evt-conflict-ws",
    )
    assert isinstance(res_conflict_ws, HostHookResult)
    assert res_conflict_ws.disposition == "deny"
    assert res_conflict_ws.reason_code == "invalid_workspace"

    # Conflicting session IDs -> fail closed
    res_conflict_sess = adapt_antigravity_pre_tool_use(
        {
            "tool_name": "run_command",
            "workspace": "/ws",
            "conversation_id": "c1",
            "session_id": "c2",
        },
        event_id="evt-conflict-sess",
    )
    assert isinstance(res_conflict_sess, HostHookResult)
    assert res_conflict_sess.disposition == "deny"
    assert res_conflict_sess.reason_code == "malformed_event"


def test_path_handling_rejections() -> None:
    """Canonical path validation rules are enforced through adapter."""
    for bad_path in (
        "/absolute/path.py",
        r"C:\Windows\System32",
        "C:/Windows/System32",
        r"C:rel\path.py",
        r"\\server\share\file.py",
        "src/../../escape.py",
        r"src\..\escape.py",
        "src/file.py\x00suffix",
    ):
        res = adapt_antigravity_pre_tool_use(
            {
                "tool_name": "write_to_file",
                "workspace": "/ws",
                "tool_input": {"TargetFile": bad_path},
            },
            event_id="evt-bad-path",
        )
        assert isinstance(res, HostHookResult)
        assert res.disposition == "deny"
        assert res.reason_code == "malformed_event"


def test_privacy_and_summary_boundedness() -> None:
    """Sensitive inputs (secrets, commands) are not echoed in summaries."""
    sentinel_path = "/private/SECRET_TOKEN/forbidden/file.py"
    sentinel_tool = "totally-secret-tool-name"
    sentinel_cmd = "rm -rf /SECRET_COMMAND_EXEC"

    # Bad path summary check
    r_path = adapt_antigravity_pre_tool_use(
        {
            "tool": "write_to_file",
            "workspace": "/ws",
            "tool_input": {"TargetFile": sentinel_path},
        },
        event_id="e1",
    )
    assert isinstance(r_path, HostHookResult)
    assert sentinel_path not in r_path.summary
    assert "SECRET_TOKEN" not in r_path.summary

    # Unsupported tool summary check
    r_tool = adapt_antigravity_pre_tool_use(
        {"tool": sentinel_tool, "workspace": "/ws"}, event_id="e2"
    )
    assert isinstance(r_tool, HostHookResult)
    assert sentinel_tool not in r_tool.summary

    # Run command with secret command line
    r_cmd = adapt_antigravity_pre_tool_use(
        {
            "tool": "run_command",
            "workspace": "/ws",
            "tool_input": {"CommandLine": sentinel_cmd},
        },
        event_id="e3",
    )
    assert isinstance(r_cmd, HostHookEvent)
    assert "SECRET_COMMAND" not in str(r_cmd)


def test_fail_closed_on_malformed_inputs() -> None:
    """Non-mapping, missing keys, unsupported tools fail closed."""
    # Non-mapping
    r1 = adapt_antigravity_pre_tool_use("not a dict", event_id="e1")
    assert isinstance(r1, HostHookResult)
    assert r1.disposition == "deny"
    assert r1.reason_code == "malformed_event"

    # Missing tool
    r2 = adapt_antigravity_pre_tool_use({"workspace": "/ws"}, event_id="e2")
    assert isinstance(r2, HostHookResult)
    assert r2.disposition == "deny"
    assert r2.reason_code == "malformed_event"

    # Unsupported tool
    r3 = adapt_antigravity_pre_tool_use(
        {"tool": "unknown_custom_tool", "workspace": "/ws"}, event_id="e3"
    )
    assert isinstance(r3, HostHookResult)
    assert r3.disposition == "deny"
    assert r3.reason_code == "unsupported_action"

    # Missing workspace
    r4 = adapt_antigravity_pre_tool_use({"tool": "run_command"}, event_id="e4")
    assert isinstance(r4, HostHookResult)
    assert r4.disposition == "deny"
    assert r4.reason_code == "invalid_workspace"

    # Invalid event_id
    r5 = adapt_antigravity_pre_tool_use(
        {"tool": "run_command", "workspace": "/ws"}, event_id=""
    )
    assert isinstance(r5, HostHookResult)
    assert r5.disposition == "deny"
    assert r5.reason_code == "malformed_event"


def test_authority_resistance() -> None:
    """Host payload cannot inject or override authority fields."""
    spoofed = {
        "tool": "write_to_file",
        "workspace": "/ws",
        "tool_input": {"TargetFile": "src/a.py"},
        "schema_version": 999,
        "phase": "post_task",
        "source": "spoofed_source",
        "mutation_class": "read_only",
        "model_digest": "sha256:fake",
        "model_name": "gpt-5",
        "execution_profile": {"profile": "fake"},
        "repository": "fake/repo",
        "state_dir": "/fake/state",
        "policy_id": "bypass",
        "scaling_pin_id": "pin-1",
        "runtime_context": "fake_ctx",
    }
    evt = adapt_antigravity_pre_tool_use(spoofed, event_id="evt-spoof")
    assert isinstance(evt, HostHookEvent)
    assert evt.schema_version == 1
    assert evt.phase == "pre_action"
    assert evt.source == "antigravity"
    assert evt.action.mutation_class == "workspace_mutation"
    assert not hasattr(evt, "model_digest")
    assert not hasattr(evt, "policy_id")


def test_render_antigravity_pre_tool_use_result() -> None:
    """Result rendering projects allow/deny accurately and rejects others."""
    allow_res = HostHookResult(
        schema_version=1,
        event_id="e1",
        disposition="allow",
        reason_code="verification_passed",
        summary="Action allowed by policy",
    )
    rendered_allow = render_antigravity_pre_tool_use_result(allow_res)
    assert rendered_allow == {
        "decision": "allow",
        "status": "allow",
        "action": "allow",
        "reason": "Action allowed by policy",
    }

    deny_res = HostHookResult(
        schema_version=1,
        event_id="e2",
        disposition="deny",
        reason_code="malformed_event",
        summary="Malformed tool input",
    )
    rendered_deny = render_antigravity_pre_tool_use_result(deny_res)
    assert rendered_deny == {
        "decision": "deny",
        "status": "deny",
        "action": "deny",
        "reason": "Malformed tool input",
    }

    # Reject non-pre-action dispositions
    for bad_disp in ("continue", "retry", "abort"):
        other_res = HostHookResult(
            schema_version=1,
            event_id="e3",
            disposition=bad_disp,  # type: ignore[arg-type]
            reason_code="not_applicable",
            summary="test",
        )
        with pytest.raises(
            ValueError,
            match="Unsupported pre-action disposition for Antigravity",
        ):
            render_antigravity_pre_tool_use_result(other_res)

    with pytest.raises(
        ValueError, match="result must be an instance of HostHookResult"
    ):
        render_antigravity_pre_tool_use_result(
            {"fake": "dict"}  # type: ignore[arg-type]
        )
