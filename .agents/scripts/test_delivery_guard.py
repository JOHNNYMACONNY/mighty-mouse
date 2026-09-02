#!/usr/bin/env python3
"""
Unit tests for delivery_guard.py safety hook script.
Runs representative PreToolUse JSON payloads through delivery_guard.py stdin.
"""

import sys
import json
import subprocess
import tempfile
import shutil
import unittest
from pathlib import Path

GUARD_SCRIPT = Path(__file__).parent / "delivery_guard.py"

class TestDeliveryGuard(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.auto_dir = Path(self.test_dir) / ".autonomous-delivery"
        self.conv_dir = self.auto_dir / "conversations"
        self.runs_dir = self.auto_dir / "runs"
        self.conv_dir.mkdir(parents=True, exist_ok=True)
        self.runs_dir.mkdir(parents=True, exist_ok=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def run_guard(self, payload: dict) -> tuple[int, dict]:
        has_ws = (
            "workspace_path" in payload
            or "cwd" in payload
            or "workspacePaths" in payload
        )
        if not has_ws:
            payload["workspace_path"] = self.test_dir

        proc = subprocess.Popen(
            [sys.executable, str(GUARD_SCRIPT)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = proc.communicate(input=json.dumps(payload))
        
        try:
            res = json.loads(stdout.strip())
        except Exception:
            res = {"decision": "unknown", "stdout": stdout, "stderr": stderr}

        return proc.returncode, res

    def setup_run(self, conv_id: str, run_id: str, state_kv: dict):
        conv_file = self.conv_dir / f"{conv_id}.json"
        conv_file.write_text(json.dumps({"run_id": run_id}))

        run_path = self.runs_dir / run_id
        run_path.mkdir(parents=True, exist_ok=True)

        lines = [f"{k}: \"{v}\"" for k, v in state_kv.items()]
        (run_path / "state.yaml").write_text("\n".join(lines))

    # --- 1. Direct Loading / Unmapped Conversation ---
    def test_unmapped_conversation_denies_file_edits(self):
        payload = {
            "tool_name": "replace_file_content",
            "tool_input": {"TargetFile": f"{self.test_dir}/src/main.py"},
            "conversation_id": "conv-unmapped"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn("outside of an active /deliver", res.get("reason", ""))

    def test_unmapped_conversation_denies_mutating_command(self):
        payload = {
            "tool_name": "run_command",
            "tool_input": {"CommandLine": "git commit -m 'unauthorized'"},
            "conversation_id": "conv-unmapped"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")

    def test_unmapped_conversation_allows_read_only_command(self):
        payload = {
            "tool_name": "run_command",
            "tool_input": {"CommandLine": "git status"},
            "conversation_id": "conv-unmapped"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 0)
        self.assertEqual(res.get("decision"), "allow")

    # --- 2. Dry-Run Mode Enforcement ---
    def test_dry_run_allows_run_artifact_writes(self):
        self.setup_run("conv-dry", "run-dry-1", {"dry_run": "true", "plan_status": "PENDING"})
        artifact_path = str((self.runs_dir / "run-dry-1" / "plan.md").resolve())
        payload = {
            "tool_name": "write_to_file",
            "tool_input": {"TargetFile": artifact_path},
            "conversation_id": "conv-dry"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 0)
        self.assertEqual(res.get("decision"), "allow")

    def test_dry_run_denies_source_file_edits(self):
        self.setup_run("conv-dry", "run-dry-1", {"dry_run": "true", "plan_status": "READY"})
        payload = {
            "tool_name": "replace_file_content",
            "tool_input": {"TargetFile": (
                        f"{self.test_dir}/src/mighty_mouse/v2/policy.py"
                    )},
            "conversation_id": "conv-dry"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn("prohibited during --dry-run", res.get("reason", ""))

    def test_dry_run_allows_allowlisted_commands(self):
        self.setup_run("conv-dry", "run-dry-1", {"dry_run": "true"})
        for cmd in ["git status", "git diff", "pytest eval/", "python3 -m pytest eval/"]:
            payload = {
                "tool_name": "run_command",
                "tool_input": {"CommandLine": cmd},
                "conversation_id": "conv-dry"
            }
            code, res = self.run_guard(payload)
            self.assertEqual(code, 0, f"Command '{cmd}' should be allowed")
            self.assertEqual(res.get("decision"), "allow")

    def test_dry_run_denies_mutating_commands(self):
        self.setup_run("conv-dry", "run-dry-1", {"dry_run": "true"})
        mutating_cmds = [
            "git add .",
            "git commit -m 'test'",
            "git push origin main",
            "pip install pytest",
            "rm -rf src/",
            "echo 'hacked' > src/file.py"
        ]
        for cmd in mutating_cmds:
            payload = {
                "tool_name": "run_command",
                "tool_input": {"CommandLine": cmd},
                "conversation_id": "conv-dry"
            }
            code, res = self.run_guard(payload)
            self.assertEqual(code, 1, f"Command '{cmd}' should be denied")
            self.assertEqual(res.get("decision"), "deny")

    # --- 3. Live Mode Enforcement ---
    def test_live_mode_denies_source_edits_before_plan_ready(self):
        self.setup_run("conv-live", "run-live-1", {"dry_run": "false", "plan_status": "PENDING", "capability_gate": "PASSED"})
        payload = {
            "tool_name": "replace_file_content",
            "tool_input": {"TargetFile": (
                        f"{self.test_dir}/src/mighty_mouse/v2/policy.py"
                    )},
            "conversation_id": "conv-live"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn(
            "prohibited before plan validation READY",
            res.get("reason", ""),
        )

    def test_live_mode_allows_source_edits_when_ready_and_passed(self):
        self.setup_run("conv-live", "run-live-1", {"dry_run": "false", "plan_status": "READY", "capability_gate": "PASSED"})
        payload = {
            "tool_name": "replace_file_content",
            "tool_input": {"TargetFile": (
                        f"{self.test_dir}/src/mighty_mouse/v2/policy.py"
                    )},
            "conversation_id": "conv-live"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 0)
        self.assertEqual(res.get("decision"), "allow")

    def test_live_mode_denies_git_commit_when_verification_fails(self):
        self.setup_run("conv-live", "run-live-1", {
            "dry_run": "false",
            "plan_status": "READY",
            "capability_gate": "PASSED",
            "last_exit_code": "1",
            "standards_count": "0",
            "spec_count": "0"
        })
        payload = {
            "tool_name": "run_command",
            "tool_input": {"CommandLine": "git commit -m 'fix'"},
            "conversation_id": "conv-live"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")

    def test_live_mode_allows_git_commit_when_all_checks_pass(self):
        self.setup_run("conv-live", "run-live-1", {
            "dry_run": "false",
            "plan_status": "READY",
            "capability_gate": "PASSED",
            "last_exit_code": "0",
            "standards_count": "0",
            "spec_count": "0"
        })
        payload = {
            "tool_name": "run_command",
            "tool_input": {"CommandLine": "git commit -m 'fix'"},
            "conversation_id": "conv-live"
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 0)
        self.assertEqual(res.get("decision"), "allow")

    # --- 4. Production Nested toolCall & workspacePaths Shape ---
    def test_production_nested_tool_call_unmapped_denial(self):
        payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {"TargetFile": f"{self.test_dir}/src/main.py"},
            },
            "conversationId": "conv-unmapped-prod",
            "workspacePaths": [self.test_dir],
            "stepIdx": 1,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn("outside of an active /deliver", res.get("reason", ""))

    def test_production_nested_tool_call_unmapped_command_denial(self):
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "git commit -m 'unauthorized'"},
            },
            "conversationId": "conv-unmapped-prod",
            "workspacePaths": [self.test_dir],
            "stepIdx": 1,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")

    def test_production_nested_tool_call_read_only_command_allowed(self):
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "git status"},
            },
            "conversationId": "conv-unmapped-prod",
            "workspacePaths": [self.test_dir],
            "stepIdx": 1,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 0)
        self.assertEqual(res.get("decision"), "allow")

    def test_production_nested_tool_call_dry_run_artifact_write_allowed(self):
        self.setup_run(
            "conv-prod-dry",
            "run-prod-dry-1",
            {"dry_run": "true", "plan_status": "PENDING"},
        )
        art_path = self.runs_dir / "run-prod-dry-1" / "plan.md"
        artifact_path = str(art_path.resolve())
        payload = {
            "toolCall": {
                "name": "write_to_file",
                "args": {"TargetFile": artifact_path},
            },
            "conversationId": "conv-prod-dry",
            "workspacePaths": [self.test_dir],
            "stepIdx": 2,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 0)
        self.assertEqual(res.get("decision"), "allow")

    def test_production_nested_tool_call_dry_run_source_denial(self):
        self.setup_run(
            "conv-prod-dry",
            "run-prod-dry-1",
            {"dry_run": "true", "plan_status": "READY"},
        )
        payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {
                    "TargetFile": (
                        f"{self.test_dir}/src/mighty_mouse/v2/policy.py"
                    )
                },
            },
            "conversationId": "conv-prod-dry",
            "workspacePaths": [self.test_dir],
            "stepIdx": 3,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn("prohibited during --dry-run", res.get("reason", ""))

    def test_production_nested_tool_call_live_mode_before_ready_denial(self):
        self.setup_run(
            "conv-prod-live",
            "run-prod-live-1",
            {
                "dry_run": "false",
                "plan_status": "PENDING",
                "capability_gate": "PASSED",
            },
        )
        payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {
                    "TargetFile": (
                        f"{self.test_dir}/src/mighty_mouse/v2/policy.py"
                    )
                },
            },
            "conversationId": "conv-prod-live",
            "workspacePaths": [self.test_dir],
            "stepIdx": 4,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn(
            "prohibited before plan validation READY",
            res.get("reason", ""),
        )

    def test_production_nested_tool_call_live_mode_when_ready_allowed(self):
        self.setup_run(
            "conv-prod-live",
            "run-prod-live-1",
            {
                "dry_run": "false",
                "plan_status": "READY",
                "capability_gate": "PASSED",
            },
        )
        payload = {
            "toolCall": {
                "name": "replace_file_content",
                "args": {
                    "TargetFile": (
                        f"{self.test_dir}/src/mighty_mouse/v2/policy.py"
                    )
                },
            },
            "conversationId": "conv-prod-live",
            "workspacePaths": [self.test_dir],
            "stepIdx": 5,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 0)
        self.assertEqual(res.get("decision"), "allow")

    def test_production_nested_tool_call_git_commit_verification_failure(self):
        self.setup_run("conv-prod-live", "run-prod-live-1", {
            "dry_run": "false",
            "plan_status": "READY",
            "capability_gate": "PASSED",
            "last_exit_code": "1",
            "standards_count": "0",
            "spec_count": "0",
        })
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "git commit -m 'fix'"},
            },
            "conversationId": "conv-prod-live",
            "workspacePaths": [self.test_dir],
            "stepIdx": 6,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")

    def test_production_nested_tool_call_git_commit_all_checks_pass(self):
        self.setup_run("conv-prod-live", "run-prod-live-1", {
            "dry_run": "false",
            "plan_status": "READY",
            "capability_gate": "PASSED",
            "last_exit_code": "0",
            "standards_count": "0",
            "spec_count": "0",
        })
        payload = {
            "toolCall": {
                "name": "run_command",
                "args": {"CommandLine": "git commit -m 'fix'"},
            },
            "conversationId": "conv-prod-live",
            "workspacePaths": [self.test_dir],
            "stepIdx": 7,
        }
        code, res = self.run_guard(payload)
        self.assertEqual(code, 0)
        self.assertEqual(res.get("decision"), "allow")

    def test_malformed_nested_tool_call_denial(self):
        payload_non_dict = {
            "toolCall": "not-a-dict",
            "conversationId": "conv-malformed",
            "workspacePaths": [self.test_dir],
        }
        code, res = self.run_guard(payload_non_dict)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn(
            "Malformed nested toolCall structure",
            res.get("reason", ""),
        )

        payload_bad_args = {
            "toolCall": {
                "name": "run_command",
                "args": "not-a-dict",
            },
            "conversationId": "conv-malformed",
            "workspacePaths": [self.test_dir],
        }
        code, res = self.run_guard(payload_bad_args)
        self.assertEqual(code, 1)
        self.assertEqual(res.get("decision"), "deny")
        self.assertIn("Malformed nested toolCall.args", res.get("reason", ""))

    def test_multiple_workspace_paths_resolution(self):
        self.setup_run(
            "conv-multi",
            "run-multi-1",
            {
                "dry_run": "false",
                "plan_status": "READY",
                "capability_gate": "PASSED",
            },
        )
        other_dir = tempfile.mkdtemp()
        try:
            payload = {
                "toolCall": {
                    "name": "replace_file_content",
                    "args": {
                        "TargetFile": (
                            f"{self.test_dir}/src/mighty_mouse/v2/policy.py"
                        ),
                    },
                },
                "conversationId": "conv-multi",
                "workspacePaths": [other_dir, self.test_dir],
                "stepIdx": 8,
            }
            code, res = self.run_guard(payload)
            self.assertEqual(code, 0)
            self.assertEqual(res.get("decision"), "allow")
        finally:
            shutil.rmtree(other_dir)


if __name__ == "__main__":
    unittest.main()
