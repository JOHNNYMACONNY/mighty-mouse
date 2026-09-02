"""Tests for Antigravity Production Registration Contract v1 (Ticket 10A).

Validates:
1. .agents/hooks.json conforms to Antigravity JSONHookSpec runtime schema.
2. No activation flags (MIGHTY_MOUSE_POST_ACTION_VERIFY/RECOVERY) hardcoded.
3. Matcher coverage: PreToolUse covers all 4 mutation tools, PostToolUse
   covers only file-write tools and explicitly excludes run_command.
4. Production Composite PreToolUse entrypoint enforces Delivery Guard
   deny-dominance without relying on native multi-hook dispatching.
5. Registered CLI commands (pretooluse, posttooluse) execution across
   working directories.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

from mighty_mouse.host.adapter import (
    ADAPTER_CONFIG_FILENAME,
    MCP_TOOL_CONTRACT_VERSION,
    HostAdapter,
)
from mighty_mouse_mcp.antigravity_hooks import (
    run_antigravity_composite_pre_tool_use,
    run_antigravity_pre_tool_use,
)
from mighty_mouse_mcp.server import _get_mcp_tool_signatures

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON_PATH = REPO_ROOT / ".agents" / "hooks.json"
GUARD_SCRIPT_PATH = REPO_ROOT / ".agents" / "scripts" / "delivery_guard.py"
COMPOSITE_SCRIPT_PATH = (
    REPO_ROOT / ".agents" / "scripts" / "composite_pretooluse.py"
)


def _setup_test_workspace_adapter_config(ws_path: Path) -> Path:
    """Create a valid .mighty-mouse/mcp-adapter.json in ws_path."""
    sigs = _get_mcp_tool_signatures()
    state_dir = ws_path / ".mighty-mouse"
    state_dir.mkdir(parents=True, exist_ok=True)
    cfg = HostAdapter.build_adapter_config(
        repository="JOHNNYMACONNY/mighty-mouse",
        model_digest="sha256:" + "a" * 64,
        model_class="local-small",
        effective_context_limit=32000,
        runtime_kind="antigravity",
        runtime_version="1.0.0",
        ollama_model=None,
        tool_signatures=sigs,
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    config_file = state_dir / ADAPTER_CONFIG_FILENAME
    config_file.write_text(json.dumps(cfg), encoding="utf-8")
    return config_file


def _setup_active_delivery_run(
    ws_path: Path, conv_id: str = "conv-active"
) -> None:
    """Create an active, ready delivery run for the workspace."""
    auto_dir = ws_path / ".autonomous-delivery"
    (auto_dir / "conversations").mkdir(parents=True, exist_ok=True)
    (auto_dir / "runs" / "run-1").mkdir(parents=True, exist_ok=True)
    (auto_dir / "conversations" / f"{conv_id}.json").write_text(
        json.dumps({"run_id": "run-1"})
    )
    (auto_dir / "runs" / "run-1" / "state.yaml").write_text(
        "dry_run: false\nplan_status: READY\ncapability_gate: PASSED\n"
    )


def test_hooks_json_exists_and_valid_schema() -> None:
    """Validate .agents/hooks.json exists and matches JSONHookSpec."""
    assert HOOKS_JSON_PATH.exists(), f"{HOOKS_JSON_PATH} must exist"
    content = HOOKS_JSON_PATH.read_text(encoding="utf-8")
    parsed = json.loads(content)

    assert isinstance(parsed, dict), "Top-level hooks.json must be a dict"
    expected_hooks = {
        "mighty-mouse-antigravity-pretooluse",
        "mighty-mouse-antigravity-posttooluse",
    }
    assert set(parsed.keys()) == expected_hooks, (
        f"hooks.json must contain exactly {expected_hooks}"
    )


def test_hooks_json_no_hardcoded_activation_flags() -> None:
    """Ensure no activation env flags are hardcoded in .agents/hooks.json."""
    content = HOOKS_JSON_PATH.read_text(encoding="utf-8")
    assert "MIGHTY_MOUSE_POST_ACTION_VERIFY" not in content, (
        "MIGHTY_MOUSE_POST_ACTION_VERIFY must not be hardcoded in config"
    )
    assert "MIGHTY_MOUSE_POST_ACTION_RECOVERY" not in content, (
        "MIGHTY_MOUSE_POST_ACTION_RECOVERY must not be hardcoded in config"
    )


def test_hooks_json_pretooluse_matcher_anchoring_and_negatives() -> None:
    """Ensure PreToolUse matcher covers 4 tools and rejects variants."""
    parsed = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    required_tools = [
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
        "run_command",
    ]
    negative_tools = [
        "write_to_file_extra",
        "prefix_write_to_file",
        "run_command_extra",
        "prefix_run_command",
        "view_file",
        "list_dir",
    ]

    pre_spec = parsed["mighty-mouse-antigravity-pretooluse"]["PreToolUse"]
    for group in pre_spec:
        matcher = group.get("matcher", "")
        pattern = re.compile(matcher)
        for tool in required_tools:
            msg = f"PreToolUse matcher '{matcher}' must match '{tool}'"
            assert pattern.search(tool), msg
        for tool in negative_tools:
            msg = f"PreToolUse matcher '{matcher}' must NOT match '{tool}'"
            assert not pattern.search(tool), msg


def test_hooks_json_posttooluse_matcher_anchoring_and_negatives() -> None:
    """Ensure PostToolUse covers file writes and rejects variants."""
    parsed = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    file_write_tools = [
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
    ]
    negative_tools = [
        "run_command",
        "run_command_extra",
        "write_to_file_extra",
        "prefix_write_to_file",
        "multi_replace_file_content_extra",
        "view_file",
    ]

    post_spec = parsed["mighty-mouse-antigravity-posttooluse"]["PostToolUse"]
    for group in post_spec:
        matcher = group.get("matcher", "")
        pattern = re.compile(matcher)
        for tool in file_write_tools:
            msg = f"PostToolUse matcher '{matcher}' must match '{tool}'"
            assert pattern.search(tool), msg
        for tool in negative_tools:
            msg = f"PostToolUse matcher '{matcher}' must NOT match '{tool}'"
            assert not pattern.search(tool), msg


def test_hooks_json_command_spec_structure() -> None:
    """Verify all hook handlers specify type='command' with valid commands."""
    parsed = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    for hook_name, spec in parsed.items():
        for event_key in ("PreToolUse", "PostToolUse"):
            if event_key in spec:
                for group in spec[event_key]:
                    hooks = group.get("hooks", [])
                    assert isinstance(hooks, list) and len(hooks) > 0, (
                        f"Hook '{hook_name}' {event_key} hooks list empty"
                    )
                    for handler in hooks:
                        assert handler.get("type") == "command", (
                            f"Hook '{hook_name}' handler invalid type"
                        )
                        cmd = handler.get("command", "")
                        assert isinstance(cmd, str) and cmd.strip(), (
                            f"Hook '{hook_name}' handler command empty string"
                        )


def test_composite_pretooluse_delivery_guard_denial_dominates(
    tmp_path: Path,
) -> None:
    """When Delivery Guard denies, overall decision is deny."""
    _setup_test_workspace_adapter_config(tmp_path)
    # Note: no active delivery run setup, so delivery guard will deny
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/module.py",
                "CodeContent": "x = 1\n",
            },
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "unmapped-conv",
        "stepIdx": 1,
    }
    raw_input = json.dumps(payload)

    # 1. Verify Mighty Mouse alone would allow (adapter config is present)
    mm_out = run_antigravity_pre_tool_use(raw_input)
    assert mm_out["decision"] == "allow"

    # 2. Execute production composite entrypoint via subprocess
    proc = subprocess.run(
        [sys.executable, str(COMPOSITE_SCRIPT_PATH)],
        input=raw_input,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0, f"Composite script failed: {proc.stderr}"
    res = json.loads(proc.stdout.strip())
    assert res["decision"] == "deny"
    assert "outside of an active /deliver" in res["reason"]

    # 3. Direct function invocation
    direct_res = run_antigravity_composite_pre_tool_use(
        raw_input,
        guard_checker=lambda _: (False, "Delivery Guard explicit test denial"),
    )
    assert direct_res["decision"] == "deny"
    assert direct_res["reason"] == "Delivery Guard explicit test denial"


def test_composite_pretooluse_mighty_mouse_denial_dominates(
    tmp_path: Path,
) -> None:
    """When Delivery Guard allows but PreToolUse denies, decision is deny."""
    # Active delivery run setup so guard allows, but NO adapter config
    _setup_active_delivery_run(tmp_path, "conv-active")

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/module.py",
                "CodeContent": "x = 1\n",
            },
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "conv-active",
        "stepIdx": 1,
    }
    raw_input = json.dumps(payload)

    # Subprocess execution
    proc = subprocess.run(
        [sys.executable, str(COMPOSITE_SCRIPT_PATH)],
        input=raw_input,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    res = json.loads(proc.stdout.strip())
    assert res["decision"] == "deny"
    assert res["reason"] == "Runtime context unavailable"


def test_composite_pretooluse_both_allow(tmp_path: Path) -> None:
    """When both gates allow, overall decision is allow."""
    _setup_test_workspace_adapter_config(tmp_path)
    _setup_active_delivery_run(tmp_path, "conv-active")

    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/module.py",
                "CodeContent": "x = 1\n",
            },
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "conv-active",
        "stepIdx": 1,
    }
    raw_input = json.dumps(payload)

    proc = subprocess.run(
        [sys.executable, str(COMPOSITE_SCRIPT_PATH)],
        input=raw_input,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    res = json.loads(proc.stdout.strip())
    assert res["decision"] == "allow"
    valid_reasons = ("Action allowed by policy", "Action is not applicable")
    assert res["reason"] in valid_reasons


def test_composite_pretooluse_both_deny(tmp_path: Path) -> None:
    """When both deny, Delivery Guard short-circuits with deny."""
    # No adapter config and no active run -> both deny
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/module.py",
                "CodeContent": "x = 1\n",
            },
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "unmapped-conv",
        "stepIdx": 1,
    }
    raw_input = json.dumps(payload)

    proc = subprocess.run(
        [sys.executable, str(COMPOSITE_SCRIPT_PATH)],
        input=raw_input,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    res = json.loads(proc.stdout.strip())
    assert res["decision"] == "deny"
    assert "outside of an active /deliver" in res["reason"]


def test_composite_pretooluse_preserves_ask_decision(
    tmp_path: Path, monkeypatch
) -> None:
    """When PreToolUse returns ask/force_ask, composite preserves it."""
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/module.py"},
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "conv-ask",
    }
    raw_input = json.dumps(payload)

    import mighty_mouse_mcp.antigravity_hooks as ag_hooks

    # When guard allows and mm returns ask
    monkeypatch.setattr(
        ag_hooks,
        "run_antigravity_pre_tool_use",
        lambda *_, **__: {
            "decision": "ask",
            "reason": "User confirmation required",
        },
    )

    res = run_antigravity_composite_pre_tool_use(
        raw_input,
        guard_checker=lambda _: (True, "Guard allowed"),
    )
    assert res["decision"] == "ask"
    assert res["reason"] == "User confirmation required"


def test_registered_composite_pretooluse_command_across_cwd(
    tmp_path: Path,
) -> None:
    """Verify registered PreToolUse command runs across root and .agents."""
    _setup_test_workspace_adapter_config(tmp_path)
    _setup_active_delivery_run(tmp_path, "conv-cwd")

    parsed = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    pre_spec = parsed["mighty-mouse-antigravity-pretooluse"]["PreToolUse"]
    cmd = pre_spec[0]["hooks"][0]["command"]

    payload = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "git status"},
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "conv-cwd",
    }
    raw_input = json.dumps(payload)

    # Execution from repo root
    proc_root = subprocess.run(
        ["sh", "-c", cmd],
        cwd=str(REPO_ROOT),
        input=raw_input,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_root.returncode == 0, (
        f"Root execution failed: {proc_root.stderr}"
    )
    res_root = json.loads(proc_root.stdout.strip())
    assert res_root["decision"] == "allow"

    # Execution from .agents directory
    proc_agents = subprocess.run(
        ["sh", "-c", cmd],
        cwd=str(REPO_ROOT / ".agents"),
        input=raw_input,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_agents.returncode == 0, (
        f".agents execution failed: {proc_agents.stderr}"
    )
    res_agents = json.loads(proc_agents.stdout.strip())
    assert res_agents["decision"] == "allow"


def test_registered_cli_posttooluse_execution(tmp_path: Path) -> None:
    """Execute mighty-mouse-antigravity-posttooluse returning strictly {}."""
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/module.py",
            },
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "cli-conv",
        "stepIdx": 2,
    }
    proc = subprocess.run(
        ["sh", "-c", "mighty-mouse-antigravity-posttooluse"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    res = json.loads(proc.stdout.strip())
    assert res == {}, "PostToolUse output must strictly project to {}"


def test_composite_pretooluse_preserves_force_ask_decision(
    tmp_path: Path, monkeypatch
) -> None:
    """When PreToolUse returns force_ask, composite preserves it."""
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {"TargetFile": "src/module.py"},
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "conv-force-ask",
    }
    raw_input = json.dumps(payload)

    import mighty_mouse_mcp.antigravity_hooks as ag_hooks

    monkeypatch.setattr(
        ag_hooks,
        "run_antigravity_pre_tool_use",
        lambda *_, **__: {
            "decision": "force_ask",
            "reason": "Force user confirmation",
        },
    )

    res = run_antigravity_composite_pre_tool_use(
        raw_input,
        guard_checker=lambda _: (True, "Guard allowed"),
    )
    assert res["decision"] == "force_ask"
    assert res["reason"] == "Force user confirmation"


def test_composite_pretooluse_malformed_stdin_fails_closed() -> None:
    """Malformed stdin to composite script returns bounded deny with code 0."""
    proc = subprocess.run(
        [sys.executable, str(COMPOSITE_SCRIPT_PATH)],
        input="{not valid json",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    res = json.loads(proc.stdout.strip())
    assert res["decision"] == "deny"
    assert "Malformed" in res["reason"]


def test_composite_pretooluse_import_failure_fails_closed() -> None:
    """If canonical composition import fails, script returns bounded deny."""
    code = (
        "import sys, runpy; "
        "sys.modules['mighty_mouse_mcp.antigravity_hooks'] = None; "
        f"runpy.run_path('{COMPOSITE_SCRIPT_PATH}', run_name='__main__')"
    )
    proc = subprocess.run(
        [sys.executable, "-c", code],
        input="{}",
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    res = json.loads(proc.stdout.strip())
    assert res["decision"] == "deny"
    assert "execution failure" in res["reason"]
