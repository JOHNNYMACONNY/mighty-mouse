import subprocess
import os

def run_test(checklist_content):
    with open("TEMP_CHECKLIST.md", "w") as f:
        f.write(checklist_content)
    
    result = subprocess.run(["python3", "src/orchestrator/enforce_workflow.py", "TEMP_CHECKLIST.md"], capture_output=True, text=True)
    os.remove("TEMP_CHECKLIST.md")
    return result.returncode == 0, result.stdout

def test_rejection():
    print("Running Orchestrator Rejection Tests...")
    
    case1 = "## Phase 1: Planning\nContent\n---\n## Phase 2: Activity\nContent\n---"
    passed, out = run_test(case1)
    assert not passed, "FAIL: Should have rejected missing Phase 3"
    print("Case 1 (Missing Section) REJECTED as expected.")

    case2 = "## Phase 1: Planning\n<Actual Result>\n---\n## Phase 2: Activity\nDone\n---\n## Phase 3: Verification\nDone"
    passed, out = run_test(case2)
    assert not passed, "FAIL: Should have rejected placeholders"
    print("Case 2 (Placeholder) REJECTED as expected.")

    case3 = "## Phase 1: Planning\nshort\n---\n## Phase 2: Activity\nshort\n---\n## Phase 3: Verification\nshort"
    passed, out = run_test(case3)
    assert not passed, "FAIL: Should have rejected short content"
    print("Case 3 (Short Content) REJECTED as expected.")

    case4 = """## Phase 1: Planning
This is a detailed plan with more than twenty characters to pass the length check.
---
## Phase 2: Activity
This is a detailed activity log with more than twenty characters to pass the length check.
---
## Phase 3: Verification
This is a detailed verification log with more than twenty characters to pass the length check.
"""
    passed, out = run_test(case4)
    assert passed, f"FAIL: Should have accepted valid checklist. Output: {out}"
    print("Case 4 (Valid Checklist) ACCEPTED as expected.")

    print("\nALL REJECTION TESTS PASSED (100% Integrity)")

if __name__ == "__main__":
    test_rejection()
