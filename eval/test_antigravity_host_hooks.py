"""Tests for Antigravity PreToolUse/PostToolUse host hook leaf adapter v1."""

from __future__ import annotations

import os
import tempfile

import pytest

from mighty_mouse.host.antigravity import (
    adapt_antigravity_post_tool_use,
    adapt_antigravity_pre_tool_use,
    render_antigravity_post_tool_use_result,
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
    # Tool aliases (flat only, no nested toolCall)
    for key in ("tool_name", "tool", "name"):
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

    # Session ID aliases including camelCase conversationId
    for key in ("conversationId", "conversation_id", "session_id"):
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
            "conversationId": "c1",
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
    """Result rendering projects controlled reason codes and rejects others."""
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
        "reason": "Verification passed",
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
        "reason": "Malformed host event",
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


def test_renderer_privacy_leakage_resistance() -> None:
    """Renderer ignores raw HostHookResult.summary and uses mapped reason."""
    # Deny side with sensitive summary
    deny_leak = HostHookResult(
        schema_version=1,
        event_id="e-leak-deny",
        disposition="deny",
        reason_code="malformed_event",
        summary="SECRET_COMMAND /private/token raw verifier output",
    )
    rendered_deny = render_antigravity_pre_tool_use_result(deny_leak)
    assert "SECRET_COMMAND" not in str(rendered_deny)
    assert "/private/token" not in str(rendered_deny)
    assert "raw verifier output" not in str(rendered_deny)
    assert rendered_deny["reason"] == "Malformed host event"

    # Allow side with sensitive summary
    allow_leak = HostHookResult(
        schema_version=1,
        event_id="e-leak-allow",
        disposition="allow",
        reason_code="verification_passed",
        summary="SECRET_ALLOW_INTERNAL /sensitive/allow/path pass detail",
    )
    rendered_allow = render_antigravity_pre_tool_use_result(allow_leak)
    assert "SECRET_ALLOW_INTERNAL" not in str(rendered_allow)
    assert "/sensitive/allow/path" not in str(rendered_allow)
    assert "pass detail" not in str(rendered_allow)
    assert rendered_allow["reason"] == "Verification passed"


# --- Production nested PreToolUse tests ---


def test_nested_tool_call_valid_pre_tool_use() -> None:
    """Production nested toolCall:{name,args} maps to correct event."""
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/module.py",
                "CodeContent": "pass",
            },
        },
        "workspacePaths": ["/path/to/ws"],
        "conversationId": "conv-production-1",
        "stepIdx": 3,
    }
    evt = adapt_antigravity_pre_tool_use(payload, event_id="evt-nested-1")
    assert isinstance(evt, HostHookEvent)
    assert evt.phase == "pre_action"
    assert evt.source == "antigravity"
    assert evt.workspace == "/path/to/ws"
    assert evt.session_id == "conv-production-1"
    assert evt.action.kind == "file_write"
    assert evt.action.mutation_class == "workspace_mutation"
    assert evt.action.target_paths == ("src/module.py",)


def test_nested_tool_call_run_command() -> None:
    """Nested toolCall for run_command: command text never in event."""
    payload = {
        "toolCall": {
            "name": "run_command",
            "args": {
                "CommandLine": "SECRET_CMD_nested",
                "Cwd": "/path/to/ws",
            },
        },
        "workspacePaths": ["/path/to/ws"],
        "conversationId": "conv-2",
        "stepIdx": 7,
    }
    evt = adapt_antigravity_pre_tool_use(payload, event_id="evt-nested-rc")
    assert isinstance(evt, HostHookEvent)
    assert evt.action.kind == "shell_command"
    assert evt.action.mutation_class == "unknown"
    assert evt.action.target_paths == ()
    assert "SECRET_CMD_nested" not in str(evt)


def test_nested_tool_call_contradicts_flat_tool_name() -> None:
    """Nested toolCall.name vs flat alias contradiction -> deny."""
    payload = {
        "toolCall": {"name": "write_to_file", "args": {}},
        "tool_name": "run_command",
        "workspace": "/ws",
    }
    r = adapt_antigravity_pre_tool_use(payload, event_id="evt-tc-conflict")
    assert isinstance(r, HostHookResult)
    assert r.disposition == "deny"
    assert r.reason_code == "malformed_event"


def test_nested_tool_call_malformed() -> None:
    """Malformed toolCall (not a dict, missing name, bad args) -> deny."""
    # toolCall is not a mapping
    r1 = adapt_antigravity_pre_tool_use(
        {"toolCall": "write_to_file", "workspace": "/ws"},
        event_id="e1",
    )
    assert isinstance(r1, HostHookResult)
    assert r1.disposition == "deny"

    # toolCall.name missing
    r2 = adapt_antigravity_pre_tool_use(
        {"toolCall": {"args": {}}, "workspace": "/ws"},
        event_id="e2",
    )
    assert isinstance(r2, HostHookResult)
    assert r2.disposition == "deny"

    # toolCall.name is empty string
    r3 = adapt_antigravity_pre_tool_use(
        {"toolCall": {"name": "  ", "args": {}}, "workspace": "/ws"},
        event_id="e3",
    )
    assert isinstance(r3, HostHookResult)
    assert r3.disposition == "deny"

    # toolCall.args is not a mapping
    r4 = adapt_antigravity_pre_tool_use(
        {
            "toolCall": {"name": "write_to_file", "args": ["bad"]},
            "workspace": "/ws",
        },
        event_id="e4",
    )
    assert isinstance(r4, HostHookResult)
    assert r4.disposition == "deny"


def test_workspace_paths_list_valid() -> None:
    """workspacePaths list accepted; first entry is canonical workspace."""
    payload = {
        "tool": "run_command",
        "workspacePaths": ["/ws/main", "/ws/secondary"],
        "stepIdx": 0,
    }
    evt = adapt_antigravity_pre_tool_use(payload, event_id="evt-wpl")
    assert isinstance(evt, HostHookEvent)
    assert evt.workspace == "/ws/main"


def test_workspace_paths_list_invalid() -> None:
    """Invalid workspacePaths entries -> deny."""
    # Empty list
    r1 = adapt_antigravity_pre_tool_use(
        {"tool": "run_command", "workspacePaths": []},
        event_id="e1",
    )
    assert isinstance(r1, HostHookResult)
    assert r1.disposition == "deny"
    assert r1.reason_code == "invalid_workspace"

    # Non-list
    r2 = adapt_antigravity_pre_tool_use(
        {"tool": "run_command", "workspacePaths": "/single/string"},
        event_id="e2",
    )
    assert isinstance(r2, HostHookResult)
    assert r2.disposition == "deny"
    assert r2.reason_code == "invalid_workspace"

    # Entry with empty string
    r3 = adapt_antigravity_pre_tool_use(
        {"tool": "run_command", "workspacePaths": [""]},
        event_id="e3",
    )
    assert isinstance(r3, HostHookResult)
    assert r3.disposition == "deny"
    assert r3.reason_code == "invalid_workspace"

    # Entry that is not a string
    r4 = adapt_antigravity_pre_tool_use(
        {"tool": "run_command", "workspacePaths": [None]},
        event_id="e4",
    )
    assert isinstance(r4, HostHookResult)
    assert r4.disposition == "deny"
    assert r4.reason_code == "invalid_workspace"


def test_absolute_target_relativization_single_workspace() -> None:
    """Absolute TargetFile in one workspace -> relativized canonical path."""
    with tempfile.TemporaryDirectory() as ws:
        target = os.path.join(ws, "src", "module.py")
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": target, "CodeContent": "pass"},
            },
            "workspacePaths": [ws],
            "conversationId": "conv-abs-1",
        }
        evt = adapt_antigravity_pre_tool_use(payload, event_id="evt-abs")
        assert isinstance(evt, HostHookEvent)
        assert evt.action.kind == "file_write"
        # Must be workspace-relative, no absolute path
        assert not os.path.isabs(evt.action.target_paths[0])
        assert evt.action.target_paths[0] == "src/module.py"
        # Absolute path not exposed
        assert ws not in evt.action.target_paths[0]


def test_absolute_target_outside_all_workspaces() -> None:
    """Absolute TargetFile outside all workspaces -> deny."""
    with tempfile.TemporaryDirectory() as ws:
        outside = "/tmp/outside_target_file.py"
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": outside},
            },
            "workspacePaths": [ws],
        }
        r = adapt_antigravity_pre_tool_use(payload, event_id="evt-outside")
        assert isinstance(r, HostHookResult)
        assert r.disposition == "deny"
        assert r.reason_code == "malformed_event"
        assert outside not in r.summary


def test_absolute_target_multiple_workspace_ambiguity() -> None:
    """Absolute TargetFile inside multiple workspaces -> deny (ambiguous)."""
    with tempfile.TemporaryDirectory() as parent:
        child = os.path.join(parent, "nested")
        os.makedirs(child, exist_ok=True)
        target = os.path.join(child, "file.py")
        payload = {
            "tool": "write_to_file",
            "workspacePaths": [parent, child],
            "tool_input": {"TargetFile": target},
        }
        r = adapt_antigravity_pre_tool_use(payload, event_id="evt-ambig")
        assert isinstance(r, HostHookResult)
        assert r.disposition == "deny"
        assert r.reason_code == "malformed_event"


def test_symlink_absolute_target_containment() -> None:
    """Symlink to workspace member -> contained via realpath resolution."""
    with tempfile.TemporaryDirectory() as ws:
        real_file = os.path.join(ws, "real_file.py")
        open(real_file, "w").close()  # create file
        link_path = os.path.join(ws, "link_file.py")
        try:
            os.symlink(real_file, link_path)
        except OSError:
            pytest.skip("symlink creation not supported")
        payload = {
            "tool": "write_to_file",
            "workspacePaths": [ws],
            "tool_input": {"TargetFile": link_path},
        }
        evt = adapt_antigravity_pre_tool_use(payload, event_id="evt-symlink")
        assert isinstance(evt, HostHookEvent)
        assert not os.path.isabs(evt.action.target_paths[0])


def test_symlink_workspace_escape_denied() -> None:
    """Symlink pointing outside workspace -> containment check fails."""
    with tempfile.TemporaryDirectory() as ws:
        with tempfile.TemporaryDirectory() as outside:
            outside_file = os.path.join(outside, "secret.py")
            open(outside_file, "w").close()
            link_path = os.path.join(ws, "escape_link.py")
            try:
                os.symlink(outside_file, link_path)
            except OSError:
                pytest.skip("symlink creation not supported")
            payload = {
                "tool": "write_to_file",
                "workspacePaths": [ws],
                "tool_input": {"TargetFile": link_path},
            }
            r = adapt_antigravity_pre_tool_use(
                payload, event_id="evt-escape"
            )
            assert isinstance(r, HostHookResult)
            assert r.disposition == "deny"


def test_step_idx_valid_and_invalid() -> None:
    """stepIdx must be non-negative int or absent; bool/negative fails."""
    # Valid stepIdx
    p_valid = {
        "tool": "run_command",
        "workspace": "/ws",
        "stepIdx": 0,
    }
    evt = adapt_antigravity_pre_tool_use(p_valid, event_id="evt-sidx-ok")
    assert isinstance(evt, HostHookEvent)

    # stepIdx absent -> OK
    p_absent = {"tool": "run_command", "workspace": "/ws"}
    evt2 = adapt_antigravity_pre_tool_use(p_absent, event_id="evt-sidx-abs")
    assert isinstance(evt2, HostHookEvent)


def test_backward_compatible_flat_payloads() -> None:
    """Legacy flat payloads remain fully supported."""
    # Old-style flat payload with tool_name / workspace_path / tool_input
    legacy = {
        "tool_name": "replace_file_content",
        "workspace_path": "/legacy/ws",
        "tool_input": {"TargetFile": "src/old.py"},
        "conversation_id": "legacy-conv",
    }
    evt = adapt_antigravity_pre_tool_use(legacy, event_id="evt-legacy")
    assert isinstance(evt, HostHookEvent)
    assert evt.workspace == "/legacy/ws"
    assert evt.session_id == "legacy-conv"
    assert evt.action.kind == "file_write"
    assert evt.action.target_paths == ("src/old.py",)


def test_conversationId_camelcase() -> None:
    """camelCase conversationId recognized as session_id."""
    payload = {
        "tool": "run_command",
        "workspace": "/ws",
        "conversationId": "camel-conv-123",
    }
    evt = adapt_antigravity_pre_tool_use(payload, event_id="evt-camel")
    assert isinstance(evt, HostHookEvent)
    assert evt.session_id == "camel-conv-123"


def test_conversationId_and_session_id_conflict() -> None:
    """conversationId and session_id with different values -> deny."""
    payload = {
        "tool": "run_command",
        "workspace": "/ws",
        "conversationId": "id-A",
        "session_id": "id-B",
    }
    r = adapt_antigravity_pre_tool_use(payload, event_id="evt-sid-conflict")
    assert isinstance(r, HostHookResult)
    assert r.disposition == "deny"
    assert r.reason_code == "malformed_event"


# --- PostToolUse tests ---


def test_post_tool_use_valid_write_tool() -> None:
    """Valid PostToolUse write tool -> phase=post_action observation."""
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/x.py"},
        },
        "workspacePaths": ["/ws"],
        "conversationId": "conv-post-1",
        "stepIdx": 5,
    }
    evt = adapt_antigravity_post_tool_use(payload, event_id="evt-post-1")
    assert isinstance(evt, HostHookEvent)
    assert evt.phase == "post_action"
    assert evt.source == "antigravity"
    assert evt.workspace == "/ws"
    assert evt.action.kind == "file_write"
    assert evt.action.target_paths == ()


def test_post_tool_use_valid_run_command() -> None:
    """Valid PostToolUse run_command -> post_action observation."""
    payload = {
        "toolCall": {"name": "run_command", "args": {}},
        "workspacePaths": ["/ws"],
        "stepIdx": 2,
    }
    evt = adapt_antigravity_post_tool_use(payload, event_id="evt-post-rc")
    assert isinstance(evt, HostHookEvent)
    assert evt.phase == "post_action"
    assert evt.action.kind == "shell_command"


def test_post_tool_use_with_error_field() -> None:
    """PostToolUse with error field -> post_action; error not echoed."""
    payload = {
        "tool": "run_command",
        "workspace": "/ws",
        "error": "SECRET_ERROR_CONTENT /path/secret 500",
        "stepIdx": 1,
    }
    evt = adapt_antigravity_post_tool_use(payload, event_id="evt-post-err")
    assert isinstance(evt, HostHookEvent)
    assert evt.phase == "post_action"
    # Error content must not appear in canonical event string
    assert "SECRET_ERROR_CONTENT" not in str(evt)


def test_post_tool_use_without_error_field() -> None:
    """PostToolUse without error field -> valid post_action observation."""
    payload = {
        "tool": "run_command",
        "workspace": "/ws",
        "stepIdx": 0,
    }
    evt = adapt_antigravity_post_tool_use(payload, event_id="evt-post-noerr")
    assert isinstance(evt, HostHookEvent)
    assert evt.phase == "post_action"


def test_post_tool_use_malformed_step_idx() -> None:
    """Malformed stepIdx in PostToolUse -> deny."""
    for bad_idx in (True, -1, "5", 1.5, None):
        if bad_idx is None:
            continue  # None means absent, not malformed
        r = adapt_antigravity_post_tool_use(
            {
                "tool": "run_command",
                "workspace": "/ws",
                "stepIdx": bad_idx,
            },
            event_id="evt-post-bad-idx",
        )
        assert isinstance(r, HostHookResult), f"expected deny for {bad_idx!r}"
        assert r.disposition == "deny"
        assert r.reason_code == "malformed_event"


def test_post_tool_use_malformed_inputs() -> None:
    """Non-mapping and missing required fields -> deny in PostToolUse."""
    r1 = adapt_antigravity_post_tool_use("not a dict", event_id="e1")
    assert isinstance(r1, HostHookResult)
    assert r1.disposition == "deny"

    r2 = adapt_antigravity_post_tool_use({}, event_id="e2")
    assert isinstance(r2, HostHookResult)
    assert r2.disposition == "deny"
    assert r2.reason_code == "malformed_event"

    r3 = adapt_antigravity_post_tool_use(
        {"tool": "run_command"}, event_id="e3"
    )
    assert isinstance(r3, HostHookResult)
    assert r3.disposition == "deny"
    assert r3.reason_code == "invalid_workspace"


def test_post_tool_use_renderer_returns_empty_dict() -> None:
    """PostToolUse render output is strictly {}."""
    payload = {
        "toolCall": {"name": "run_command", "args": {}},
        "workspacePaths": ["/ws"],
    }
    evt = adapt_antigravity_post_tool_use(payload, event_id="evt-render")
    assert isinstance(evt, HostHookEvent)
    out = render_antigravity_post_tool_use_result(evt)
    assert out == {}

    # Also works on HostHookResult (deny path)
    deny_result = HostHookResult(
        schema_version=1,
        event_id="e-deny",
        disposition="deny",
        reason_code="malformed_event",
        summary="test",
    )
    out2 = render_antigravity_post_tool_use_result(deny_result)
    assert out2 == {}


def test_post_tool_use_renderer_rejects_invalid_input() -> None:
    """PostToolUse renderer rejects non-event/result input."""
    with pytest.raises(ValueError, match="HostHookEvent or HostHookResult"):
        render_antigravity_post_tool_use_result(  # type: ignore
            {"not": "valid"}
        )


def test_post_tool_use_privacy_no_payload_echo() -> None:
    """PostToolUse canonical event never echoes payload/error content."""
    payload = {
        "tool": "run_command",
        "workspace": "/ws",
        "error": "PRIVATE_ERROR_TEXT",
        "tool_input": {"CommandLine": "SECRET_NESTED_CMD"},
        "stepIdx": 0,
    }
    result = adapt_antigravity_post_tool_use(payload, event_id="evt-priv")
    result_str = str(result)
    assert "PRIVATE_ERROR_TEXT" not in result_str
    assert "SECRET_NESTED_CMD" not in result_str
    out = render_antigravity_post_tool_use_result(result)
    assert out == {}
    assert "PRIVATE_ERROR_TEXT" not in str(out)
