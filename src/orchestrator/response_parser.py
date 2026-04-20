import re
import os

class ResponseParser:
    @staticmethod
    def parse_and_write(raw_text):
        # 1. Extract CHECKLIST.md
        # Look for a block starting with # Mighty Mouse Checklist or similar
        checklist_match = re.search(r'# Mighty Mouse Checklist.*?(?=```|$)', raw_text, re.DOTALL | re.IGNORECASE)
        if checklist_match:
            checklist_content = checklist_match.group(0).strip()
            with open("CHECKLIST.md", "w") as f:
                f.write(checklist_content)
                f.write("\n")

        # 2. Extract files from code blocks
        # Support formats:
        # ```python:filename.py
        # ```python
        # # filename.py
        # ```
        # pattern matches: ```lang[:filename]\n(content)\n```
        file_blocks = re.finditer(r'```(?P<lang>\w+)?(?::(?P<path>[^\n]+))?\n(?P<content>.*?)\n```', raw_text, re.DOTALL)
        
        extracted_files = []
        for block in file_blocks:
            path = block.group('path')
            content = block.group('content')
            
            # If path is not in the block header, check for # filename.py on the first line
            if not path:
                first_line = content.split('\n')[0].strip()
                if first_line.startswith('#') or first_line.startswith('//'):
                    potential_path = first_line.lstrip('#/ ').strip()
                    if '.' in potential_path and len(potential_path.split()) == 1:
                        path = potential_path
                        # Optionally remove the comment line from content? 
                        # Better to keep it for safety unless it's strictly a path.
            
            if path:
                path = path.strip()
                # Special case: don't overwrite CHECKLIST.md if it was in a code block
                if path.lower() == "checklist.md":
                    continue
                
                # Ensure directory exists
                os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
                
                with open(path, "w") as f:
                    f.write(content)
                extracted_files.append(path)
        
        return extracted_files

if __name__ == "__main__":
    # Smoke test
    test_text = """
# Mighty Mouse Checklist - test_task
## Phase 1: Planning
- [x] Done.
---
## Phase 2: Activity
- [x] Solved.
---
## Phase 3: Verification
- [x] Verified.

```python:math_lib.py
def add(a, b):
    return a + b
```

```python
# utils.py
def log(m):
    print(m)
```
"""
    files = ResponseParser.parse_and_write(test_text)
    print(f"Extracted files: {files}")
    if os.path.exists("math_lib.py"): os.remove("math_lib.py")
    if os.path.exists("utils.py"): os.remove("utils.py")
    if os.path.exists("CHECKLIST.md"): os.remove("CHECKLIST.md")
