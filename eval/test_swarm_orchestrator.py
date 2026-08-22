import json
import os
import sys
import unittest

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))

try:
    from mighty_mouse.orchestrator.swarm import (
        SwarmPlanner,
        SwarmCoder,
        SwarmReviewer,
        SwarmOrchestrator,
    )
except ImportError:
    from swarm import (  # noqa: F401
        SwarmPlanner,
        SwarmCoder,
        SwarmReviewer,
        SwarmOrchestrator,
    )


class MockOllamaClient:
    def __init__(self, responses=None):
        self.responses = responses or {}
        self.call_count = 0

    def generate(self, prompt, system_prompt="", temperature=0.0):
        self.call_count += 1
        if "SWARM PLANNER ROLE" in system_prompt:
            return """<swarm_plan>
## 1. Task Understanding
Implement simple visitor pattern.

## 2. Mandatory Dependency Audit
- visitor.py (NEW)

## 3. Authorized File Impact Map
- visitor.py (NEW)

## 4. Implementation Steps
1. Create visitor class.
</swarm_plan>"""

        if "SWARM CODER ROLE" in system_prompt:
            return """<act>
[FILE: visitor.py]
```python
class Visitor:
    def visit(self):
        return "visited"
```
</act>"""

        if "SWARM REVIEWER ROLE" in system_prompt:
            return """<swarm_review>
VERDICT: PASS
REASON: Tests passed.
</swarm_review>"""

        return "Mock response"


class TestSwarmOrchestrator(unittest.TestCase):
    def setUp(self):
        self.mock_client = MockOllamaClient()
        self.task_data = {
            "id": "task_test_001",
            "instruction": "Create visitor class in visitor.py",
            "context": "No existing files."
        }

    @staticmethod
    def _make_recording_adapter(ws, calls, output_path="visitor.py"):
        """Return an adapter that records calls and writes output_path."""
        from pathlib import Path as _Path

        def adapter(canonical_response: str):
            calls.append(canonical_response)
            (_Path(ws) / output_path).write_text(
                "class Visitor: pass\n"
            )
            return [output_path]

        return adapter

    def test_swarm_planner(self):
        planner = SwarmPlanner(ollama_client=self.mock_client)
        res = planner.plan(self.task_data)
        self.assertIn("plan_text", res)
        self.assertIn("visitor.py", res["authorized_files"])
        self.assertIsInstance(json.dumps(res), str)

    def test_swarm_coder(self):
        coder = SwarmCoder(ollama_client=self.mock_client)
        plan_info = {"plan_text": "Authorized file: visitor.py"}
        res = coder.code(self.task_data, plan_info)
        self.assertIn("visitor.py", res["file_updates"])
        self.assertEqual(res["planned_output_paths"], ["visitor.py"])
        self.assertIsNotNone(res["response_plan"])
        self.assertEqual(len(res["warnings"]), 0)
        # Verify JSON serializability of coder result
        self.assertIsInstance(json.dumps(res), str)

    def test_swarm_coder_canonical_fenced_response_planning(self):
        class CanonicalFencedClient:
            def generate(self, prompt, system_prompt="", temperature=0.0):
                return "```python:answer.py\nanswer = True\n```"

        coder = SwarmCoder(ollama_client=CanonicalFencedClient())
        result = coder.code(
            self.task_data,
            {"plan_text": "Authorized file: answer.py"},
            workspace_root="/tmp/swarm-workspace",
        )

        self.assertEqual(
            result["file_updates"],
            {"answer.py": "answer = True"},
        )
        self.assertEqual(result["planned_output_paths"], ["answer.py"])
        self.assertIsNotNone(result["response_plan"])
        self.assertEqual(len(result["warnings"]), 0)
        self.assertIsInstance(json.dumps(result), str)

    def test_swarm_coder_legacy_file_block_planning(self):
        class LegacyBlockClient:
            def generate(self, prompt, system_prompt="", temperature=0.0):
                return (
                    "<act>\n[FILE: answer.py]\n"
                    "```python\nanswer = True\n```\n</act>"
                )

        coder = SwarmCoder(ollama_client=LegacyBlockClient())
        result = coder.code(
            self.task_data,
            {"plan_text": "Authorized file: answer.py"},
            workspace_root="/tmp/swarm-workspace",
        )

        self.assertEqual(
            result["file_updates"],
            {"answer.py": "answer = True"},
        )
        self.assertEqual(result["planned_output_paths"], ["answer.py"])
        self.assertIsNotNone(result["response_plan"])
        self.assertEqual(len(result["warnings"]), 0)
        self.assertIsInstance(json.dumps(result), str)

    def test_swarm_coder_legacy_absolute_path_rejection(self):
        class AbsolutePathClient:
            def generate(self, prompt, system_prompt="", temperature=0.0):
                return (
                    "<act>\n[FILE: /tmp/outside.py]\n"
                    "```python\nval = 1\n```\n</act>"
                )

        coder = SwarmCoder(ollama_client=AbsolutePathClient())
        result = coder.code(
            self.task_data,
            {"plan_text": "Outside"},
            workspace_root="/tmp/safe",
        )
        self.assertTrue(
            any(
                "Absolute paths are not allowed" in w
                for w in result["warnings"]
            )
        )
        self.assertEqual(result["file_updates"], {})
        self.assertEqual(result["planned_output_paths"], [])
        self.assertIsNone(result["response_plan"])
        self.assertIsInstance(json.dumps(result), str)

    def test_swarm_coder_legacy_traversal_rejection(self):
        class TraversalClient:
            def generate(self, prompt, system_prompt="", temperature=0.0):
                return (
                    "<act>\n[FILE: ../escaped.py]\n"
                    "```python\nmalicious = True\n```\n</act>"
                )

        coder = SwarmCoder(ollama_client=TraversalClient())
        res = coder.code(
            self.task_data,
            {"plan_text": "Escape"},
            workspace_root="/tmp/safe",
        )
        self.assertTrue(
            any(
                "Parent traversal is not allowed" in w
                for w in res["warnings"]
            )
        )
        self.assertEqual(res["file_updates"], {})
        self.assertEqual(res["planned_output_paths"], [])
        self.assertIsNone(res["response_plan"])
        self.assertIsInstance(json.dumps(res), str)

    def test_swarm_coder_legacy_mighty_protection_enforced(self):
        class MightyHarnessClient:
            def generate(self, prompt, system_prompt="", temperature=0.0):
                return (
                    "<act>\n[FILE: .mighty/secret.json]\n"
                    "```json\n{}\n```\n</act>"
                )

        coder = SwarmCoder(ollama_client=MightyHarnessClient())
        res = coder.code(
            self.task_data,
            {"plan_text": "Touch mighty"},
            workspace_root="/tmp/safe",
        )
        self.assertEqual(res["file_updates"], {})
        self.assertEqual(res["planned_output_paths"], [])
        self.assertEqual(len(res["warnings"]), 0)
        self.assertIsInstance(json.dumps(res), str)

    def test_swarm_coder_is_strictly_non_mutating_on_workspace(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            sentinel_file = ws / "existing.py"
            sentinel_file.write_text(
                "INITIAL_STATE = True\n",
                encoding="utf-8",
            )
            to_delete = ws / "old.py"
            to_delete.write_text("DELETE_ME = True\n", encoding="utf-8")

            snapshot_before = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*")
                if p.is_file()
            }

            class MutatingAttemptClient:
                def generate(self, prompt, system_prompt="", temperature=0.0):
                    return (
                        "```python:existing.py\nOVERWRITTEN = True\n```\n\n"
                        "```python:new_file.py\nCREATED = True\n```"
                    )

            coder = SwarmCoder(ollama_client=MutatingAttemptClient())
            res = coder.code(
                self.task_data,
                {
                    "plan_text": (
                        "Plan modifying existing.py and creating new_file.py"
                    )
                },
                workspace_root=str(ws),
            )

            snapshot_after = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*")
                if p.is_file()
            }

            # 1. Byte-for-byte exact equality on all files in workspace
            self.assertEqual(snapshot_before, snapshot_after)
            # 2. Sentinel existing file was not modified
            self.assertEqual(
                sentinel_file.read_text(encoding="utf-8"),
                "INITIAL_STATE = True\n",
            )
            # 3. Target delete file was not deleted
            self.assertTrue(to_delete.exists())
            self.assertEqual(
                to_delete.read_text(encoding="utf-8"),
                "DELETE_ME = True\n",
            )
            # 4. Planned new file was not created on disk
            self.assertFalse((ws / "new_file.py").exists())
            # 5. Output structure reflects planned paths without side effects
            self.assertIn("existing.py", res["planned_output_paths"])
            self.assertIn("new_file.py", res["planned_output_paths"])
            self.assertEqual(len(res["warnings"]), 0)
            self.assertIsInstance(json.dumps(res), str)

    def test_swarm_coder_planned_deletes_require_authorization(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            to_delete = ws / "unauthorized.py"
            to_delete.write_text("STILL_HERE = True\n", encoding="utf-8")

            class DeleteAttemptClient:
                def generate(self, prompt, system_prompt="", temperature=0.0):
                    return "```delete:unauthorized.py\n```"

            coder = SwarmCoder(ollama_client=DeleteAttemptClient())
            res = coder.code(
                self.task_data,
                {"plan_text": "Delete"},
                workspace_root=str(ws),
            )

            # Unauthorized delete yields warning and does not delete file
            self.assertTrue(to_delete.exists())
            self.assertEqual(
                to_delete.read_text(encoding="utf-8"),
                "STILL_HERE = True\n",
            )
            self.assertTrue(
                any("Deletion not permitted" in w for w in res["warnings"])
            )
            self.assertIsInstance(json.dumps(res), str)

    def test_swarm_orchestrator_caller_inventory(self):
        from pathlib import Path

        repo_root = Path(_REPO_ROOT)
        src_root = repo_root / "src" / "mighty_mouse"
        mcp_root = repo_root / "mcp" / "src"

        production_files = (
            list(src_root.rglob("*.py")) + list(mcp_root.rglob("*.py"))
        )
        swarm_callers = []

        for pf in production_files:
            rel = str(pf.relative_to(repo_root))
            if rel.endswith("orchestrator/swarm.py"):
                continue
            content = pf.read_text(encoding="utf-8")
            if any(
                sym in content
                for sym in (
                    "SwarmPlanner",
                    "SwarmCoder",
                    "SwarmReviewer",
                    "SwarmOrchestrator",
                )
            ):
                swarm_callers.append(rel)

        expected = ["src/mighty_mouse/orchestrator/mighty_mouse_agent.py"]
        self.assertEqual(sorted(swarm_callers), sorted(expected))

    def test_swarm_reviewer_pass(self):
        reviewer = SwarmReviewer(ollama_client=self.mock_client)
        verif = {
            "status": "success",
            "scope": "PASS",
            "adherence": "PASS",
            "test_logs": "1 passed",
        }
        res = reviewer.review(verif)
        self.assertEqual(res["verdict"], "PASS")
        self.assertEqual(res["feedback"], "")
        self.assertIsInstance(json.dumps(res), str)

    def test_swarm_reviewer_reject_with_feedback(self):
        reviewer = SwarmReviewer(ollama_client=self.mock_client)
        verif = {
            "status": "failed",
            "scope": "FAIL",
            "adherence": "PASS",
            "reason": "Unauthorized file edit: /etc/passwd",
            "test_logs": "FAILED test_visitor.py",
        }
        res = reviewer.review(verif)
        self.assertEqual(res["verdict"], "REJECT")
        self.assertIn("SCOPE VIOLATION", res["feedback"])
        self.assertIsInstance(json.dumps(res), str)

    def test_swarm_orchestrator_sequential_pipeline_is_non_mutating(self):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            sentinel = ws / "baseline.py"
            sentinel.write_text("BASE = 1\n", encoding="utf-8")

            snapshot_before = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*")
                if p.is_file()
            }

            orchestrator = SwarmOrchestrator(
                concurrency=1,
                ollama_client=self.mock_client,
            )
            res = orchestrator.execute_swarm_pipeline(
                self.task_data,
                verifier_func=None,
            )
            self.assertEqual(res["review"]["verdict"], "PASS")
            self.assertEqual(res["turn"], 1)
            self.assertIn(
                "visitor.py",
                res["coder"]["planned_output_paths"],
            )

            snapshot_after = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*")
                if p.is_file()
            }
            self.assertEqual(snapshot_before, snapshot_after)
            # Verify full pipeline result is JSON serializable
            self.assertIsInstance(json.dumps(res), str)

    def test_swarm_orchestrator_concurrent_dual_slot_pipeline_non_mutating(
        self,
    ):
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            sentinel = ws / "baseline.py"
            sentinel.write_text("BASE = 1\n", encoding="utf-8")

            snapshot_before = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*")
                if p.is_file()
            }

            orchestrator = SwarmOrchestrator(
                concurrency=2,
                ollama_client=self.mock_client,
            )
            res = orchestrator.execute_swarm_pipeline(
                self.task_data,
                verifier_func=None,
            )
            self.assertEqual(res["review"]["verdict"], "PASS")
            self.assertEqual(res["turn"], 1)
            self.assertIn(
                "visitor.py",
                res["coder"]["planned_output_paths"],
            )

            snapshot_after = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*")
                if p.is_file()
            }
            self.assertEqual(snapshot_before, snapshot_after)
            # Verify concurrent pipeline result is JSON serializable
            self.assertIsInstance(json.dumps(res), str)

    def test_swarm_cli_dispatcher_json_serialization_characterization(self):
        orchestrator = SwarmOrchestrator(
            concurrency=1,
            ollama_client=self.mock_client,
        )
        res = orchestrator.execute_swarm_pipeline(
            self.task_data,
            verifier_func=None,
        )
        serialized = json.dumps(res, indent=2)
        self.assertIsInstance(serialized, str)
        loaded = json.loads(serialized)
        self.assertEqual(loaded["review"]["verdict"], "PASS")
        self.assertIn("visitor.py", loaded["coder"]["planned_output_paths"])
        self.assertIn("operations", loaded["coder"]["response_plan"])

    # ------------------------------------------------------------------
    # Ticket 2: winner-only application boundary tests
    # ------------------------------------------------------------------

    def test_winner_application_adapter_called_exactly_once_on_pass(self):
        """Single candidate / PASS: adapter called once with canonical resp."""
        import tempfile
        from pathlib import Path

        adapter_calls = []

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            fake_adapter = self._make_recording_adapter(
                ws, adapter_calls
            )

            orchestrator = SwarmOrchestrator(
                concurrency=1,
                ollama_client=self.mock_client,
            )
            res = orchestrator.execute_swarm_pipeline(
                self.task_data,
                verifier_func=None,
                application_adapter=fake_adapter,
            )

        self.assertEqual(res["review"]["verdict"], "PASS")
        # Adapter called exactly once
        self.assertEqual(len(adapter_calls), 1)
        # Correct canonical response passed (contains visitor.py path)
        self.assertIn("visitor.py", adapter_calls[0])
        # Application metadata accurate
        self.assertTrue(res["application"]["available"])
        self.assertTrue(res["application"]["occurred"])
        self.assertIn(
            "visitor.py", res["application"]["applied_output_paths"]
        )
        # Result remains JSON serializable
        self.assertIsInstance(json.dumps(res), str)

    def test_two_slot_selection_loser_never_applied(self):
        """Two-slot: both candidates non-mutating; only winner applied once."""
        import tempfile
        from pathlib import Path

        adapter_calls = []

        class SlotTrackingClient:
            """Returns distinct responses per slot to allow tracking."""

            def __init__(self):
                self._call = 0

            def generate(self, prompt, system_prompt="", temperature=0.0):
                self._call += 1
                if "SWARM PLANNER ROLE" in system_prompt:
                    return (
                        "<swarm_plan>\n## 1. Task Understanding\n"
                        "Implement visitor.\n\n"
                        "## 3. Authorized File Impact Map\n"
                        "- visitor.py (NEW)\n</swarm_plan>"
                    )
                if "SWARM CODER ROLE" in system_prompt:
                    # slot 0 uses temperature 0.0, slot 1 uses 0.15
                    # Return same path so min(warnings) selection is stable
                    return (
                        "```python:visitor.py\nclass Visitor: pass\n```"
                    )
                if "SWARM REVIEWER ROLE" in system_prompt:
                    return (
                        "<swarm_review>\nVERDICT: PASS\n"
                        "REASON: ok\n</swarm_review>"
                    )
                return ""

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            fake_adapter = self._make_recording_adapter(
                ws, adapter_calls
            )

            orchestrator = SwarmOrchestrator(
                concurrency=2,
                ollama_client=SlotTrackingClient(),
            )
            res = orchestrator.execute_swarm_pipeline(
                self.task_data,
                verifier_func=None,
                application_adapter=fake_adapter,
            )

        self.assertEqual(res["review"]["verdict"], "PASS")
        # Adapter called exactly once (winner only)
        self.assertEqual(len(adapter_calls), 1)
        self.assertTrue(res["application"]["occurred"])
        self.assertIsInstance(json.dumps(res), str)

    def test_reviewer_reject_adapter_not_called_workspace_unchanged(self):
        """Reviewer REJECT: adapter not called, workspace unchanged."""
        import tempfile
        from pathlib import Path

        adapter_calls = []

        class AlwaysRejectClient:
            def generate(self, prompt, system_prompt="", temperature=0.0):
                if "SWARM PLANNER ROLE" in system_prompt:
                    return (
                        "<swarm_plan>Plan</swarm_plan>"
                    )
                if "SWARM CODER ROLE" in system_prompt:
                    return (
                        "```python:visitor.py\nclass V: pass\n```"
                    )
                if "SWARM REVIEWER ROLE" in system_prompt:
                    return (
                        "<swarm_review>\nVERDICT: REJECT\n"
                        "REASON: Fail\n</swarm_review>"
                    )
                return ""

        def reject_verifier(task_data, coder_result):
            return {
                "status": "failed",
                "scope": "FAIL",
                "adherence": "FAIL",
                "reason": "Tests failed",
                "test_logs": "FAILED",
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            sentinel = ws / "safe.py"
            sentinel.write_text("SAFE = True\n")
            snapshot_before = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*") if p.is_file()
            }

            def fake_adapter(canonical_response: str):
                adapter_calls.append(canonical_response)
                return []

            orchestrator = SwarmOrchestrator(
                concurrency=1,
                ollama_client=AlwaysRejectClient(),
            )
            res = orchestrator.execute_swarm_pipeline(
                self.task_data,
                max_retries=1,
                verifier_func=reject_verifier,
                application_adapter=fake_adapter,
            )

            snapshot_after = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*") if p.is_file()
            }

        self.assertEqual(res["review"]["verdict"], "REJECT")
        # Adapter never called
        self.assertEqual(len(adapter_calls), 0)
        # Workspace unchanged
        self.assertEqual(snapshot_before, snapshot_after)
        # Application metadata reflects no application
        self.assertFalse(res["application"]["occurred"])
        self.assertIsInstance(json.dumps(res), str)

    def test_all_retries_rejected_application_call_count_zero(self):
        """All retries rejected: adapter call count == 0."""
        adapter_calls = []

        class AlwaysRejectClient:
            def generate(self, prompt, system_prompt="", temperature=0.0):
                if "SWARM PLANNER ROLE" in system_prompt:
                    return "<swarm_plan>Plan</swarm_plan>"
                if "SWARM CODER ROLE" in system_prompt:
                    return "```python:visitor.py\nclass V: pass\n```"
                if "SWARM REVIEWER ROLE" in system_prompt:
                    return (
                        "<swarm_review>\nVERDICT: REJECT\n"
                        "REASON: Fail\n</swarm_review>"
                    )
                return ""

        def reject_verifier(task_data, coder_result):
            return {
                "status": "failed",
                "scope": "FAIL",
                "adherence": "FAIL",
                "reason": "Tests failed",
                "test_logs": "FAILED",
            }

        orchestrator = SwarmOrchestrator(
            concurrency=1,
            ollama_client=AlwaysRejectClient(),
        )
        res = orchestrator.execute_swarm_pipeline(
            self.task_data,
            max_retries=3,
            verifier_func=reject_verifier,
            application_adapter=lambda r: adapter_calls.append(r) or [],
        )

        self.assertEqual(len(adapter_calls), 0)
        self.assertFalse(res["application"]["occurred"])
        self.assertIsInstance(json.dumps(res), str)

    def test_no_application_adapter_behavior_remains_non_mutating(self):
        """No adapter: pipeline stays planning-only, workspace unchanged."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            sentinel = ws / "baseline.py"
            sentinel.write_text("BASE = 1\n")
            snapshot_before = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*") if p.is_file()
            }

            orchestrator = SwarmOrchestrator(
                concurrency=1,
                ollama_client=self.mock_client,
            )
            res = orchestrator.execute_swarm_pipeline(
                self.task_data,
                verifier_func=None,
                # No application_adapter — Ticket 1 invariant preserved
            )

            snapshot_after = {
                p.relative_to(ws): p.read_bytes()
                for p in ws.rglob("*") if p.is_file()
            }

        self.assertEqual(snapshot_before, snapshot_after)
        self.assertFalse(res["application"]["available"])
        self.assertFalse(res["application"]["occurred"])
        self.assertEqual(res["application"]["applied_output_paths"], [])
        self.assertIsInstance(json.dumps(res), str)

    def test_winner_canonical_write_creates_file_exactly_once(self):
        """Winner write: file created by adapter exactly once."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            write_count = [0]

            def writing_adapter(canonical_response: str):
                from mighty_mouse.orchestrator.response_application import (
                    ResponseApplicationPolicy,
                    ResponseApplicationRequest,
                    apply_response,
                )
                policy = ResponseApplicationPolicy(
                    workspace_root=str(ws)
                )
                req = ResponseApplicationRequest(
                    raw_response=canonical_response, policy=policy
                )
                written = apply_response(req)
                write_count[0] += len(written)
                return written

            orchestrator = SwarmOrchestrator(
                concurrency=1,
                ollama_client=self.mock_client,
            )
            res = orchestrator.execute_swarm_pipeline(
                self.task_data,
                verifier_func=None,
                application_adapter=writing_adapter,
            )

        self.assertEqual(res["review"]["verdict"], "PASS")
        self.assertTrue(res["application"]["occurred"])
        # visitor.py written exactly once
        self.assertEqual(write_count[0], 1)
        self.assertIn(
            "visitor.py", res["application"]["applied_output_paths"]
        )
        self.assertIsInstance(json.dumps(res), str)

    def test_winner_authorized_delete_applied_once(self):
        """Authorized delete: winner deletes only the allowed path."""
        import tempfile
        from pathlib import Path

        with tempfile.TemporaryDirectory() as tmpdir:
            ws = Path(tmpdir)
            to_delete = ws / "old.py"
            to_delete.write_text("OLD = True\n")
            keeper = ws / "keep.py"
            keeper.write_text("KEEP = True\n")

            class DeleteResponseClient:
                def generate(
                    self, prompt, system_prompt="", temperature=0.0
                ):
                    if "SWARM PLANNER ROLE" in system_prompt:
                        return "<swarm_plan>Plan</swarm_plan>"
                    if "SWARM CODER ROLE" in system_prompt:
                        return "```delete:old.py\n```"
                    if "SWARM REVIEWER ROLE" in system_prompt:
                        return (
                            "<swarm_review>\nVERDICT: PASS\n"
                            "REASON: ok\n</swarm_review>"
                        )
                    return ""

            def delete_adapter(canonical_response: str):
                from mighty_mouse.orchestrator.response_application import (
                    ResponseApplicationPolicy,
                    ResponseApplicationRequest,
                    apply_response,
                )
                policy = ResponseApplicationPolicy(
                    workspace_root=str(ws),
                    allowed_delete_paths=("old.py",),
                )
                req = ResponseApplicationRequest(
                    raw_response=canonical_response, policy=policy
                )
                return apply_response(req)

            orchestrator = SwarmOrchestrator(
                concurrency=1,
                ollama_client=DeleteResponseClient(),
            )
            res = orchestrator.execute_swarm_pipeline(
                self.task_data,
                verifier_func=None,
                application_adapter=delete_adapter,
                allowed_delete_paths=("old.py",),
            )

            self.assertEqual(res["review"]["verdict"], "PASS")
            self.assertTrue(res["application"]["occurred"])
            self.assertIn(
                "old.py", res["application"]["applied_output_paths"]
            )
            # Keeper file must remain untouched
            self.assertTrue(keeper.exists())
            self.assertFalse(to_delete.exists())

        self.assertIsInstance(json.dumps(res), str)

    def test_invalid_candidate_with_no_ops_never_reaches_adapter(self):
        """Candidate with no validated operations never reaches adapter."""
        adapter_calls = []

        class EmptyResponseClient:
            def generate(
                self, prompt, system_prompt="", temperature=0.0
            ):
                if "SWARM PLANNER ROLE" in system_prompt:
                    return "<swarm_plan>Plan</swarm_plan>"
                if "SWARM CODER ROLE" in system_prompt:
                    # No valid code blocks with paths
                    return "No files to generate."
                if "SWARM REVIEWER ROLE" in system_prompt:
                    return (
                        "<swarm_review>\nVERDICT: PASS\n"
                        "REASON: ok\n</swarm_review>"
                    )
                return ""

        orchestrator = SwarmOrchestrator(
            concurrency=1,
            ollama_client=EmptyResponseClient(),
        )
        res = orchestrator.execute_swarm_pipeline(
            self.task_data,
            verifier_func=None,
            application_adapter=lambda r: adapter_calls.append(r) or [],
        )

        # Adapter not called because no validated operations exist
        self.assertEqual(len(adapter_calls), 0)
        self.assertFalse(res["application"]["occurred"])
        self.assertIsInstance(json.dumps(res), str)

    def test_application_failure_is_visible_not_silently_swallowed(self):
        """Application exception propagates; no silent success."""

        def exploding_adapter(canonical_response: str):
            raise RuntimeError("Storage backend unavailable")

        orchestrator = SwarmOrchestrator(
            concurrency=1,
            ollama_client=self.mock_client,
        )
        with self.assertRaises(RuntimeError) as ctx:
            orchestrator.execute_swarm_pipeline(
                self.task_data,
                verifier_func=None,
                application_adapter=exploding_adapter,
            )
        self.assertIn("Storage backend unavailable", str(ctx.exception))

    def test_json_result_remains_serializable_after_application(self):
        """Applied result stays json.dumps() compatible."""

        def noop_adapter(canonical_response: str):
            return ["visitor.py"]

        orchestrator = SwarmOrchestrator(
            concurrency=1,
            ollama_client=self.mock_client,
        )
        res = orchestrator.execute_swarm_pipeline(
            self.task_data,
            verifier_func=None,
            application_adapter=noop_adapter,
        )

        serialized = json.dumps(res, indent=2)
        loaded = json.loads(serialized)
        self.assertEqual(loaded["review"]["verdict"], "PASS")
        self.assertTrue(loaded["application"]["occurred"])
        self.assertIn(
            "visitor.py", loaded["application"]["applied_output_paths"]
        )

    def test_cli_caller_no_adapter_remains_non_mutating_after_ticket2(
        self,
    ):
        """mighty_mouse_agent.py --mode swarm supplies no adapter."""
        from pathlib import Path
        import re as _re

        repo_root = Path(_REPO_ROOT)
        agent_path = (
            repo_root
            / "src"
            / "mighty_mouse"
            / "orchestrator"
            / "mighty_mouse_agent.py"
        )
        content = agent_path.read_text(encoding="utf-8")
        # The swarm pipeline call must not pass application_adapter kwarg.
        # Use [\s\S]*? to match multi-line call bodies correctly.
        pipeline_calls = _re.findall(
            r"execute_swarm_pipeline\([\s\S]*?\)",
            content,
        )
        for call in pipeline_calls:
            self.assertNotIn(
                "application_adapter=",
                call,
                "CLI swarm caller must not pass application_adapter",
            )


if __name__ == "__main__":
    unittest.main()
