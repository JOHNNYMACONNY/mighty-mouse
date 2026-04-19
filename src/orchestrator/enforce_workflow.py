import sys
import re
import os

def check_checklist(filepath):
    if not os.path.exists(filepath):
        print("FAIL: CHECKLIST.md not found.")
        return False

    with open(filepath, 'r') as f:
        content = f.read()

    # Define mandatory sections and their patterns
    sections = {
        "Planning": r"## Phase 1: Planning\n(.*?)\n---",
        "Activity": r"## Phase 2: Activity\n(.*?)\n---",
        "Verification": r"## Phase 3: Verification\n(.*)"
    }

    placeholders = [
        "<Briefly describe what needs to be built>",
        "<Technical Requirements>",
        "<summary of the work>",
        "<Actual Result>"
    ]

    for name, pattern in sections.items():
        match = re.search(pattern, content, re.DOTALL)
        if not match:
            print(f"FAIL: Missing section or invalid format for {name}")
            return False
        
        section_content = match.group(1).strip()
        
        # Check if content is too short (implies skipped or lazy)
        if len(section_content) < 20: 
            print(f"FAIL: Section {name} is empty or insufficiently detailed.")
            return False

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
