"""Tests for Antigravity Production Registration Contract v1 (Ticket 10).

Validates:
1. .agents/hooks.json conforms to Antigravity JSONHookSpec runtime schema.
2. No activation flags (MIGHTY_MOUSE_POST_ACTION_VERIFY/RECOVERY) hardcoded.
3. Matcher coverage for all mutation tools in PreToolUse and PostToolUse.
4. Delivery Guard deny-dominance composition in PreToolUse.
5. Registered CLI commands (pretooluse, posttooluse) execution.
6. Delivery Guard shell command execution resilience across directories.
"""

from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

from mighty_mouse.host.adapter import (
    ADAPTER_CONFIG_FILENAME,
    MCP_TOOL_CONTRACT_VERSION,
    HostAdapter,
)
from mighty_mouse_mcp.antigravity_hooks import run_antigravity_pre_tool_use
from mighty_mouse_mcp.server import _get_mcp_tool_signatures

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_JSON_PATH = REPO_ROOT / ".agents" / "hooks.json"
GUARD_SCRIPT_PATH = REPO_ROOT / ".agents" / "scripts" / "delivery_guard.py"


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


def _compose_pretooluse_decisions(
    guard_result: dict[str, Any],
    pre_hook_result: dict[str, Any],
) -> dict[str, Any]:
    """Compose guard and pre-hook decisions using deny-dominance."""
    guard_dec = guard_result.get("decision", "deny").lower()
    hook_dec = pre_hook_result.get("decision", "deny").lower()

    if guard_dec == "deny":
        return {
            "decision": "deny",
            "dominating_source": "delivery-guard",
            "reason": guard_result.get("reason", "Denied by delivery guard"),
        }
    if hook_dec == "deny":
        return {
            "decision": "deny",
            "dominating_source": "mighty-mouse-antigravity-pretooluse",
            "reason": pre_hook_result.get("reason", "Denied by host hook"),
        }
    return {
        "decision": "allow",
        "dominating_source": None,
        "reason": "Allowed by all PreToolUse hooks",
    }


def test_hooks_json_exists_and_valid_schema() -> None:
    """Validate .agents/hooks.json exists and matches JSONHookSpec."""
    assert HOOKS_JSON_PATH.exists(), f"{HOOKS_JSON_PATH} must exist"
    content = HOOKS_JSON_PATH.read_text(encoding="utf-8")
    parsed = json.loads(content)

    assert isinstance(parsed, dict), "Top-level hooks.json must be a dict"
    expected_hooks = {
        "delivery-guard",
        "mighty-mouse-antigravity-pretooluse",
        "mighty-mouse-antigravity-posttooluse",
    }
    msg = f"hooks.json must contain entries for {expected_hooks}"
    assert expected_hooks.issubset(set(parsed.keys())), msg


def test_hooks_json_no_hardcoded_activation_flags() -> None:
    """Ensure no activation env flags are hardcoded in .agents/hooks.json."""
    content = HOOKS_JSON_PATH.read_text(encoding="utf-8")
    assert "MIGHTY_MOUSE_POST_ACTION_VERIFY" not in content, (
        "MIGHTY_MOUSE_POST_ACTION_VERIFY must not be hardcoded in config"
    )
    assert "MIGHTY_MOUSE_POST_ACTION_RECOVERY" not in content, (
        "MIGHTY_MOUSE_POST_ACTION_RECOVERY must not be hardcoded in config"
    )


def test_hooks_json_matcher_coverage() -> None:
    """Ensure matchers cover all 4 mutation tools in pre and post hooks."""
    parsed = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    required_tools = [
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
        "run_command",
    ]

    for hook_name, spec in parsed.items():
        if "PreToolUse" in spec:
            for group in spec["PreToolUse"]:
                matcher = group.get("matcher", "")
                pattern = re.compile(matcher)
                for tool in required_tools:
                    msg = (
                        f"Hook '{hook_name}' PreToolUse matcher '{matcher}' "
                        f"must match '{tool}'"
                    )
                    assert pattern.search(tool), msg

        if "PostToolUse" in spec:
            for group in spec["PostToolUse"]:
                matcher = group.get("matcher", "")
                pattern = re.compile(matcher)
                for tool in required_tools:
                    msg = (
                        f"Hook '{hook_name}' PostToolUse matcher '{matcher}' "
                        f"must match '{tool}'"
                    )
                    assert pattern.search(tool), msg


def test_hooks_json_command_spec_structure() -> None:
    """Verify all hook handlers specify type='command' with commands."""
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


def test_deny_dominance_delivery_guard_denial_dominates(
    tmp_path: Path,
) -> None:
    """When Delivery Guard denies, overall decision is deny."""
    _setup_test_workspace_adapter_config(tmp_path)
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

    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    guard_out = json.loads(proc.stdout)
    assert guard_out["decision"] == "deny"
    assert proc.returncode == 1

    pre_out = run_antigravity_pre_tool_use(json.dumps(payload))
    assert pre_out["decision"] == "allow"

    composed = _compose_pretooluse_decisions(guard_out, pre_out)
    assert composed["decision"] == "deny"
    assert composed["dominating_source"] == "delivery-guard"


def test_deny_dominance_pre_hook_denial_dominates(tmp_path: Path) -> None:
    """When PreToolUse denies, overall decision is deny."""
    auto_dir = tmp_path / ".autonomous-delivery"
    (auto_dir / "conversations").mkdir(parents=True, exist_ok=True)
    (auto_dir / "runs" / "run-1").mkdir(parents=True, exist_ok=True)
    (auto_dir / "conversations" / "conv-active.json").write_text(
        json.dumps({"run_id": "run-1"})
    )
    (auto_dir / "runs" / "run-1" / "state.yaml").write_text(
        "dry_run: false\nplan_status: READY\ncapability_gate: PASSED\n"
    )

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

    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    guard_out = json.loads(proc.stdout)
    assert guard_out["decision"] == "allow"
    assert proc.returncode == 0

    pre_out = run_antigravity_pre_tool_use(json.dumps(payload))
    assert pre_out["decision"] == "deny"
    assert pre_out["reason"] == "Runtime context unavailable"

    composed = _compose_pretooluse_decisions(guard_out, pre_out)
    assert composed["decision"] == "deny"
    assert composed["dominating_source"] == (
        "mighty-mouse-antigravity-pretooluse"
    )


def test_deny_dominance_both_allow(tmp_path: Path) -> None:
    """When both hooks allow, overall decision is allow."""
    _setup_test_workspace_adapter_config(tmp_path)

    auto_dir = tmp_path / ".autonomous-delivery"
    (auto_dir / "conversations").mkdir(parents=True, exist_ok=True)
    (auto_dir / "runs" / "run-1").mkdir(parents=True, exist_ok=True)
    (auto_dir / "conversations" / "conv-active.json").write_text(
        json.dumps({"run_id": "run-1"})
    )
    (auto_dir / "runs" / "run-1" / "state.yaml").write_text(
        "dry_run: false\nplan_status: READY\ncapability_gate: PASSED\n"
    )

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

    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    guard_out = json.loads(proc.stdout)
    assert guard_out["decision"] == "allow"

    pre_out = run_antigravity_pre_tool_use(json.dumps(payload))
    assert pre_out["decision"] == "allow"

    composed = _compose_pretooluse_decisions(guard_out, pre_out)
    assert composed["decision"] == "allow"
    assert composed["dominating_source"] is None


def test_deny_dominance_both_deny(tmp_path: Path) -> None:
    """When both hooks deny, overall decision is deny."""
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

    proc = subprocess.run(
        [sys.executable, str(GUARD_SCRIPT_PATH)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    guard_out = json.loads(proc.stdout)
    assert guard_out["decision"] == "deny"

    pre_out = run_antigravity_pre_tool_use(json.dumps(payload))
    assert pre_out["decision"] == "deny"

    composed = _compose_pretooluse_decisions(guard_out, pre_out)
    assert composed["decision"] == "deny"


def test_registered_cli_commands_resolvable() -> None:
    """Verify registered CLI commands exist in PATH or can be invoked."""
    for cmd_name in (
        "mighty-mouse-antigravity-pretooluse",
        "mighty-mouse-antigravity-posttooluse",
    ):
        proc = subprocess.run(
            ["sh", "-c", f"command -v {cmd_name}"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert proc.returncode == 0, f"Command '{cmd_name}' must be in PATH"
        assert proc.stdout.strip(), f"Command '{cmd_name}' path non-empty"


def test_registered_cli_pretooluse_execution(tmp_path: Path) -> None:
    """Execute mighty-mouse-antigravity-pretooluse binary via subprocess."""
    _setup_test_workspace_adapter_config(tmp_path)
    payload = {
        "toolCall": {
            "name": "write_to_file",
            "args": {
                "TargetFile": "src/module.py",
                "CodeContent": "x = 1\n",
            },
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "cli-conv",
        "stepIdx": 1,
    }
    proc = subprocess.run(
        ["sh", "-c", "mighty-mouse-antigravity-pretooluse"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    res = json.loads(proc.stdout.strip())
    assert res["decision"] == "allow"


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


def test_delivery_guard_command_execution_across_cwd(tmp_path: Path) -> None:
    """Test delivery-guard command across root and .agents directories."""
    parsed = json.loads(HOOKS_JSON_PATH.read_text(encoding="utf-8"))
    guard_cmd = (
        parsed["delivery-guard"]["PreToolUse"][0]["hooks"][0]["command"]
    )

    payload = {
        "toolCall": {
            "name": "run_command",
            "args": {"CommandLine": "git status"},
        },
        "workspacePaths": [str(tmp_path)],
        "conversationId": "conv-test",
    }

    proc_root = subprocess.run(
        ["sh", "-c", guard_cmd],
        cwd=str(REPO_ROOT),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_root.returncode == 0
    res_root = json.loads(proc_root.stdout.strip())
    assert res_root["decision"] == "allow"

    proc_agents = subprocess.run(
        ["sh", "-c", guard_cmd],
        cwd=str(REPO_ROOT / ".agents"),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc_agents.returncode == 0
    res_agents = json.loads(proc_agents.stdout.strip())
    assert res_agents["decision"] == "allow"
