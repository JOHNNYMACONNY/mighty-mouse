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


def _log_warning(msg: str):
    sys.stderr.write(f"[!] Warning: {msg}\n")


def load_state(workspace_dirs: list[str] | str, conversation_id: str):
    if not conversation_id or not workspace_dirs:
        return None, None, None

    if isinstance(workspace_dirs, str):
        workspace_dirs = [workspace_dirs]

    for ws in workspace_dirs:
        if not ws:
            continue
        auto_dir = Path(ws) / ".autonomous-delivery"
        mapping_file = auto_dir / "conversations" / f"{conversation_id}.json"

        run_id = None
        if mapping_file.exists():
            try:
                data = json.loads(mapping_file.read_text())
                run_id = data.get("run_id")
            except (OSError, json.JSONDecodeError) as exc:
                _log_warning(
                    f"could not read mapping ({mapping_file}): {exc}"
                )

        if not run_id:
            active_pointer = auto_dir / "active_run"
            if active_pointer.exists():
                try:
                    run_id = active_pointer.read_text().strip()
                except OSError as exc:
                    _log_warning(
                        f"could not read active_run ({active_pointer}): {exc}"
                    )

        if run_id:
            run_dir = auto_dir / "runs" / run_id
            state_file = run_dir / "state.yaml"
            if not state_file.exists():
                return run_id, None, ws

            # Parse key-value lines from state.yaml simply
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
                _log_warning(
                    f"could not read state file ({state_file}): {exc}"
                )

            return run_id, state, ws

    primary_ws = workspace_dirs[0] if workspace_dirs else os.getcwd()
    return None, None, primary_ws


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

    mut_file_pat = r"^(rm|mv|cp|touch|chmod)\s+"
    if re.match(mut_file_pat, cmd_clean):
        return False, "File mutation command prohibited in dry-run mode."

    return False, f"Command '{cmd_clean}' is not in the dry-run allowlist."


def evaluate_tool_call(payload: dict):
    if not isinstance(payload, dict):
        emit_decision(
            False, "Denied: Malformed hook payload; expected JSON object."
        )
        return

    # Extract tool_name and tool_input from nested toolCall or flat aliases
    tool_call = payload.get("toolCall")
    if isinstance(tool_call, dict):
        tool_name = tool_call.get("name")
        args_raw = tool_call.get("args")
        if args_raw is not None and not isinstance(args_raw, dict):
            emit_decision(
                False, "Denied: Malformed nested toolCall.args; expected dict."
            )
            return
        tool_input = args_raw if isinstance(args_raw, dict) else {}
    elif "toolCall" in payload and payload.get("toolCall") is not None:
        emit_decision(False, "Denied: Malformed nested toolCall structure.")
        return
    else:
        tool_name = (
            payload.get("tool_name")
            or payload.get("tool")
            or payload.get("name")
            or payload.get("tool_call")
        )
        tool_input = (
            payload.get("tool_input")
            or payload.get("args")
            or payload.get("arguments")
            or payload.get("input")
            or {}
        )
        if not isinstance(tool_input, dict):
            tool_input = {}

    if not tool_name or not isinstance(tool_name, str):
        emit_decision(True, "Non-guarded action")
        return
    if not tool_name.strip():
        emit_decision(True, "Non-guarded action")
        return

    tool_name = tool_name.strip()

    conversation_id = (
        payload.get("conversationId")
        or payload.get("conversation_id")
        or payload.get("session_id")
        or ""
    )
    if isinstance(conversation_id, str):
        conversation_id = conversation_id.strip()
    else:
        conversation_id = ""

    workspace_paths_raw = payload.get("workspacePaths")
    if isinstance(workspace_paths_raw, list):
        workspace_candidates = [
            p.strip()
            for p in workspace_paths_raw
            if isinstance(p, str) and p.strip()
        ]
    elif isinstance(workspace_paths_raw, str) and workspace_paths_raw.strip():
        workspace_candidates = [workspace_paths_raw.strip()]
    else:
        flat_ws = (
            payload.get("workspace_path")
            or payload.get("cwd")
            or os.getcwd()
        )
        workspace_candidates = [str(flat_ws)]

    workspace_dir = (
        workspace_candidates[0] if workspace_candidates else os.getcwd()
    )

    run_id, state, matched_ws = load_state(
        workspace_candidates, conversation_id
    )
    if matched_ws:
        workspace_dir = matched_ws

    # 1. No Active Delivery Run Mapping
    if not run_id or not state:
        write_tools = [
            "write_to_file",
            "replace_file_content",
            "multi_replace_file_content",
        ]
        if tool_name in write_tools:
            emit_decision(
                False,
                "Denied: Write requested outside of an active /deliver run.",
            )
        if tool_name == "run_command":
            cmd = (
                tool_input.get("CommandLine")
                or tool_input.get("command")
                or ""
            )
            ok, reason = is_dry_run_command_allowed(cmd)
            if not ok:
                emit_decision(
                    False,
                    "Denied: Mutating shell command outside active /deliver "
                    f"workflow run: {reason}",
                )
            emit_decision(True, "Allowed read-only shell command")
        emit_decision(True, "Allowed non-mutating tool")

    is_dry_run = state.get("dry_run", "false").lower() in ["true", "1", "yes"]
    plan_status = state.get("plan_status", "PENDING").upper()
    capability_gate = state.get("capability_gate", "PENDING").upper()

    auto_base = Path(workspace_dir) / ".autonomous-delivery" / "runs"
    auto_runs_dir = (auto_base / run_id).resolve()

    def _is_inside_run_dir(path_str: str) -> bool:
        if not path_str:
            return False
        try:
            p = Path(path_str).resolve()
            return p == auto_runs_dir or auto_runs_dir in p.parents
        except Exception:
            return False

    # 2. File Edit Tools
    write_tools = [
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
    ]
    if tool_name in write_tools:
        target_file = (
            tool_input.get("TargetFile")
            or tool_input.get("file_path")
            or tool_input.get("path")
            or ""
        )
        target_abs = ""
        if target_file and isinstance(target_file, str):
            t_path = Path(target_file)
            if not t_path.is_absolute() and workspace_dir:
                target_abs = str(
                    (Path(workspace_dir) / t_path).resolve()
                )
            else:
                target_abs = str(t_path.resolve())

        if is_dry_run:
            if _is_inside_run_dir(target_abs):
                emit_decision(
                    True,
                    "Allowed artifact write inside run directory "
                    "during --dry-run.",
                )
            else:
                emit_decision(
                    False,
                    f"Denied: File write to '{target_file}' "
                    "is prohibited during --dry-run mode.",
                )

        # Live mode file write checks
        if _is_inside_run_dir(target_abs):
            emit_decision(True, "Allowed run artifact write.")

        if plan_status != "READY" or capability_gate != "PASSED":
            emit_decision(
                False,
                f"Denied: Implementation edit to '{target_file}' prohibited "
                f"before plan validation READY and capability_gate PASSED "
                f"(current plan_status={plan_status}, "
                f"capability_gate={capability_gate}).",
            )

        emit_decision(True, "Allowed implementation edit in live mode.")

    # 3. Shell Command Tool (run_command)
    if tool_name == "run_command":
        cmd = (
                tool_input.get("CommandLine")
                or tool_input.get("command")
                or ""
            )

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
