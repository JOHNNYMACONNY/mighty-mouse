import sys
import re
import os

def check_checklist(filepath):
    if not os.path.exists(filepath):
        print("FAIL: CHECKLIST.md not found.")
        return False

    with open(filepath, 'r') as f:
        content = f.read()

    # Define mandatory sections — accept both '## Phase N: Name', bare '## Name', and XML <PLANNING>
    sections = {
        "Planning":     r"(?:## Phase 1: Planning|## Planning|<PLANNING>)\n?(.*?)(?:\n---|</PLANNING>|\Z)",
        "Activity":     r"(?:## Phase 2: Activity|## Activity)\n(.*?)(?:\n---|\Z)",
        "Verification": r"(?:## Phase 3: Verification|## Verification)\n(.*)",
    }

    placeholders = [
        "<Briefly describe what needs to be built>",
        "<Technical Requirements>",
        "<summary of the work>",
        "<Actual Result>"
    ]

    # Planning is required; Activity and Verification are advisory
    required_sections = {"Planning"}
    advisory_sections = {"Activity", "Verification"}

    all_sections = {**{k: v for k, v in sections.items() if k in required_sections},
                    **{k: v for k, v in sections.items() if k in advisory_sections}}

    for name, pattern in all_sections.items():
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            if name in required_sections:
                print(f"FAIL: Missing section or invalid format for {name}")
                return False
            else:
                # Advisory — warn but don't block
                continue

        section_content = match.group(1).strip()

        # Check if content is too short (implies skipped or lazy)
        if len(section_content) < 20:
            if name in required_sections:
                print(f"FAIL: Section {name} is empty or insufficiently detailed.")
                return False
            continue

        # Check for presence of placeholders
        for p in placeholders:
            if p in section_content:
                print(f"FAIL: Section {name} still contains placeholder text '{p}'.")
                return False

    print("PASS: Workflow adherence verified.")
    return True

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 enforce_workflow.py <path_to_checklist>")
        sys.exit(1)
    
    success = check_checklist(sys.argv[1])
    sys.exit(0 if success else 1)
