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

    def test_swarm_planner(self):
        planner = SwarmPlanner(ollama_client=self.mock_client)
        res = planner.plan(self.task_data)
        self.assertIn("plan_text", res)
        self.assertIn("visitor.py", res["authorized_files"])

    def test_swarm_coder(self):
        coder = SwarmCoder(ollama_client=self.mock_client)
        plan_info = {"plan_text": "Authorized file: visitor.py"}
        res = coder.code(self.task_data, plan_info)
        self.assertIn("visitor.py", res["file_updates"])
        self.assertEqual(res["planned_output_paths"], ("visitor.py",))
        self.assertIsNotNone(res["response_plan"])
        self.assertEqual(len(res["warnings"]), 0)

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
        self.assertEqual(result["planned_output_paths"], ("answer.py",))
        self.assertIsNotNone(result["response_plan"])
        self.assertEqual(len(result["warnings"]), 0)

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
        self.assertEqual(result["planned_output_paths"], ("answer.py",))
        self.assertIsNotNone(result["response_plan"])
        self.assertEqual(len(result["warnings"]), 0)

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
        self.assertEqual(result["planned_output_paths"], ())
        self.assertIsNone(result["response_plan"])

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
        self.assertEqual(res["planned_output_paths"], ())
        self.assertIsNone(res["response_plan"])

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
        self.assertEqual(res["planned_output_paths"], ())
        self.assertEqual(len(res["warnings"]), 0)

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


if __name__ == "__main__":
    unittest.main()
