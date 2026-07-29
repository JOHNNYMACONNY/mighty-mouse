#!/usr/bin/env python3
"""
Antigravity Delivery Guard (PreToolUse Hook)

Enforces safety policies for /deliver workflow execution:
- Verifies conversationId-to-run-id mapping.
- Denies file edits and mutating shell commands if no active delivery run exists.
- In --dry-run mode:
  - Permits writes ONLY inside .autonomous-delivery/runs/<run-id>/ artifact directory.
  - Denies source, test, workflow, rule, and skill edits.
  - Denies mutating commands (git add, commit, push, reset, checkout, rm, mv, pip install, etc.) using an allowlist.
- In live mode:
  - Denies implementation edits until plan_status == READY and capability_gate == PASSED.
  - Denies git commit until tests, verification, and code review pass with zero actionable findings.
"""

import os
import sys
import json
import re
from pathlib import Path


def emit_decision(allowed: bool, reason: str = ""):
    status_str = "allow" if allowed else "deny"
    output = {
        "decision": status_str,
        "status": status_str,
        "action": status_str,
        "reason": reason if not allowed else "Operation authorized by delivery guard."
    }
    print(json.dumps(output))
    sys.exit(0 if allowed else 1)


def parse_payload():
    try:
        raw = sys.stdin.read()
        if not raw or not raw.strip():
            return {}
        return json.loads(raw)
    except Exception:
        return {}


def load_state(workspace_dir: str, conversation_id: str):
    if not conversation_id or not workspace_dir:
        return None, None

    auto_dir = Path(workspace_dir) / ".autonomous-delivery"
    mapping_file = auto_dir / "conversations" / f"{conversation_id}.json"
    
    run_id = None
    if mapping_file.exists():
        try:
            data = json.loads(mapping_file.read_text())
            run_id = data.get("run_id")
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[!] Warning: could not read conversation mapping ({mapping_file}): {exc}")

    if not run_id:
        active_pointer = auto_dir / "active_run"
        if active_pointer.exists():
            try:
                run_id = active_pointer.read_text().strip()
            except OSError as exc:
                print(f"[!] Warning: could not read active_run pointer ({active_pointer}): {exc}")

    if not run_id:
        return None, None

    state_file = auto_dir / "runs" / run_id / "state.yaml"
    if not state_file.exists():
        return run_id, None

    # Parse key-value lines from state.yaml simply without external heavy deps
    state = {}
    try:
        content = state_file.read_text()
        for line in content.splitlines():
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                parts = line.split(":", 1)
                k = parts[0].strip()
                v = parts[1].strip().strip('"').strip("'")
                state[k] = v
    except OSError as exc:
        print(f"[!] Warning: could not read state file ({state_file}): {exc}")

    return run_id, state


def is_dry_run_command_allowed(cmd: str) -> tuple[bool, str]:
    if not cmd:
        return False, "Empty command"
    
    cmd_clean = cmd.strip()

    # Block shell redirection operators and command chainers for unsafe ops
    if any(op in cmd_clean for op in [">", ">>", ";", "&&", "||"]):
        # Check if chained commands are all safe
        sub_cmds = re.split(r";|&&|\|\|", cmd_clean)
        for sub in sub_cmds:
            sub = sub.strip()
            if not sub:
                continue
            if ">" in sub:
                return False, "Redirection operator (>) is prohibited in dry-run mode."
            ok, reason = is_dry_run_command_allowed(sub)
            if not ok:
                return False, reason
        return True, "Allowed safe command chain"

    # Explicit Allowlist patterns for dry-run
    allowed_patterns = [
        r"^git\s+status(\s+.*)?$",
        r"^git\s+diff(\s+.*)?$",
        r"^git\s+log(\s+.*)?$",
        r"^git\s+rev-parse(\s+.*)?$",
        r"^git\s+branch(\s+.*)?$",
        r"^git\s+show(\s+.*)?$",
        r"^pytest(\s+.*)?$",
        r"^\.venv/bin/pytest(\s+.*)?$",
        r"^python3?\s+-m\s+pytest(\s+.*)?$",
        r"^PYTHONPATH=.*pytest(\s+.*)?$",
        r"^ls(\s+.*)?$",
        r"^cat(\s+.*)?$",
        r"^which(\s+.*)?$",
        r"^echo(\s+.*)?$",
        r"^node(\s+.*)?$",
        r"^python3?(\s+[^\-].*)?$"
    ]

    for pat in allowed_patterns:
        if re.match(pat, cmd_clean):
            return True, "Command matched dry-run allowlist"

    # Mutating command blocks
    mutating_git = ["add", "commit", "push", "reset", "checkout", "rm", "mv", "rebase", "merge", "restore", "stash", "clean"]
    for git_op in mutating_git:
        if re.match(fr"^git\s+{git_op}(\s+.*)?$", cmd_clean):
            return False, f"Git mutation 'git {git_op}' is prohibited in dry-run mode."

    if re.match(r"^(pip|npm|yarn|brew)\s+install", cmd_clean):
        return False, "Package installation is prohibited in dry-run mode."

    if re.match(r"^(rm|mv|cp|touch|chmod)\s+", cmd_clean):
        return False, "File mutation shell command is prohibited in dry-run mode."

    return False, f"Command '{cmd_clean}' is not in the dry-run allowlist."


def evaluate_tool_call(payload: dict):
    tool_name = payload.get("tool_name") or payload.get("tool") or payload.get("name") or payload.get("tool_call")
    tool_input = payload.get("tool_input") or payload.get("args") or payload.get("arguments") or payload.get("input") or {}
    conversation_id = payload.get("conversation_id") or payload.get("conversationId") or payload.get("session_id") or ""
    workspace_dir = payload.get("workspace_path") or payload.get("cwd") or os.getcwd()

    if not tool_name:
        emit_decision(True, "Non-guarded action")

    run_id, state = load_state(workspace_dir, conversation_id)

    # 1. No Active Delivery Run Mapping
    if not run_id or not state:
        if tool_name in ["write_to_file", "replace_file_content", "multi_replace_file_content"]:
            emit_decision(False, "Denied: Application write requested outside of an active /deliver workflow run.")
        if tool_name == "run_command":
            cmd = tool_input.get("CommandLine", "")
            ok, reason = is_dry_run_command_allowed(cmd)
            if not ok:
                emit_decision(False, f"Denied: Mutating shell command outside active /deliver workflow run: {reason}")
            emit_decision(True, "Allowed read-only shell command")
        emit_decision(True, "Allowed non-mutating tool")

    is_dry_run = state.get("dry_run", "false").lower() in ["true", "1", "yes"]
    plan_status = state.get("plan_status", "PENDING").upper()
    capability_gate = state.get("capability_gate", "PENDING").upper()
    
    auto_runs_dir = str((Path(workspace_dir) / ".autonomous-delivery" / "runs" / run_id).resolve())

    # 2. File Edit Tools (write_to_file, replace_file_content, multi_replace_file_content)
    if tool_name in ["write_to_file", "replace_file_content", "multi_replace_file_content"]:
        target_file = tool_input.get("TargetFile") or tool_input.get("file_path") or ""
        target_abs = str(Path(target_file).resolve()) if target_file else ""

        if is_dry_run:
            if target_abs and target_abs.startswith(auto_runs_dir):
                emit_decision(True, "Allowed artifact write inside run directory during --dry-run.")
            else:
                emit_decision(False, f"Denied: File write to '{target_file}' is prohibited during --dry-run mode.")

        # Live mode file write checks
        if target_abs and target_abs.startswith(auto_runs_dir):
            emit_decision(True, "Allowed run artifact write.")

        if plan_status != "READY" or capability_gate != "PASSED":
            emit_decision(False, f"Denied: Implementation edit to '{target_file}' prohibited before plan validation READY and capability_gate PASSED (current plan_status={plan_status}, capability_gate={capability_gate}).")

        emit_decision(True, "Allowed implementation edit in live mode.")

    # 3. Shell Command Tool (run_command)
    if tool_name == "run_command":
        cmd = tool_input.get("CommandLine", "")

        if is_dry_run:
            ok, reason = is_dry_run_command_allowed(cmd)
            if ok:
                emit_decision(True, reason)
            else:
                emit_decision(False, f"Denied in --dry-run mode: {reason}")

        # Live mode git commit checks
        if "git commit" in cmd:
            last_exit_code = state.get("last_exit_code", "1")
            standards_count = int(state.get("standards_count", "1")) if state.get("standards_count", "1").isdigit() else 1
            spec_count = int(state.get("spec_count", "1")) if state.get("spec_count", "1").isdigit() else 1
            
            if plan_status != "READY":
                emit_decision(False, "Denied: git commit prohibited before plan validation READY.")
            if last_exit_code != "0":
                emit_decision(False, "Denied: git commit prohibited while test verification fails.")
            if standards_count > 0 or spec_count > 0:
                emit_decision(False, f"Denied: git commit prohibited while unresolved code-review findings exist (standards={standards_count}, spec={spec_count}).")

        emit_decision(True, "Allowed shell command in live mode.")

    emit_decision(True, "Allowed tool call")


def main():
    payload = parse_payload()
    evaluate_tool_call(payload)


if __name__ == "__main__":
    main()
