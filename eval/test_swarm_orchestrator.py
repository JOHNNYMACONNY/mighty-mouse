import os
import sys
import unittest
from unittest.mock import MagicMock

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))

from swarm import SwarmPlanner, SwarmCoder, SwarmReviewer, SwarmOrchestrator


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
- /tmp/visitor.py (NEW)

## 3. Authorized File Impact Map
- /tmp/visitor.py (NEW)

## 4. Implementation Steps
1. Create visitor class.
</swarm_plan>"""

        if "SWARM CODER ROLE" in system_prompt:
            return """<act>
[FILE: /tmp/visitor.py]
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
            "instruction": "Create visitor class in /tmp/visitor.py",
            "context": "No existing files."
        }

    def test_swarm_planner(self):
        planner = SwarmPlanner(ollama_client=self.mock_client)
        res = planner.plan(self.task_data)
        self.assertIn("plan_text", res)
        self.assertIn("/tmp/visitor.py", res["authorized_files"])

    def test_swarm_coder(self):
        coder = SwarmCoder(ollama_client=self.mock_client)
        plan_info = {"plan_text": "Authorized file: /tmp/visitor.py"}
        res = coder.code(self.task_data, plan_info)
        self.assertIn("/tmp/visitor.py", res["file_updates"])
        self.assertEqual(len(res["warnings"]), 0)

    def test_swarm_reviewer_pass(self):
        reviewer = SwarmReviewer(ollama_client=self.mock_client)
        verif = {"status": "success", "scope": "PASS", "adherence": "PASS", "test_logs": "1 passed"}
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
            "test_logs": "FAILED test_visitor.py"
        }
        res = reviewer.review(verif)
        self.assertEqual(res["verdict"], "REJECT")
        self.assertIn("SCOPE VIOLATION", res["feedback"])

    def test_swarm_orchestrator_sequential_pipeline(self):
        orchestrator = SwarmOrchestrator(concurrency=1, ollama_client=self.mock_client)
        res = orchestrator.execute_swarm_pipeline(self.task_data)
        self.assertEqual(res["review"]["verdict"], "PASS")
        self.assertEqual(res["turn"], 1)

    def test_swarm_orchestrator_concurrent_dual_slot_pipeline(self):
        orchestrator = SwarmOrchestrator(concurrency=2, ollama_client=self.mock_client)
        res = orchestrator.execute_swarm_pipeline(self.task_data)
        self.assertEqual(res["review"]["verdict"], "PASS")
        self.assertEqual(res["turn"], 1)


if __name__ == "__main__":
    unittest.main()
