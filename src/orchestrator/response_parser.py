import re
import os

class ResponseParser:
    @staticmethod
    def parse_and_write(raw_text):
        print(f"[parser] Processing response (Length: {len(raw_text)})")
        
        # 1. Extract CHECKLIST.md
        checklist_match = re.search(r'# Mighty Mouse Checklist.*?(?=```|$)', raw_text, re.DOTALL | re.IGNORECASE)
        if checklist_match:
            checklist_content = checklist_match.group(0).strip()
            with open("CHECKLIST.md", "w") as f:
                f.write(checklist_content)
                f.write("\n")
            print("[parser] Wrote CHECKLIST.md")

        # 2. Extract files from code blocks
        # Pattern: ```lang:path\ncontent\n```
        file_blocks = re.finditer(r'```(?P<lang>\w+)?(?::(?P<path>[^\n]+))?\n(?P<content>.*?)\n```', raw_text, re.DOTALL)
        
        extracted_files = []
        for block in file_blocks:
            path = block.group('path')
            content = block.group('content')
            
            # Fallback to comment-based path identification if header is missing
            if not path:
                lines = content.split('\n')
                if lines:
                    first_line = lines[0].strip()
                    if first_line.startswith('#') or first_line.startswith('//'):
                        potential = first_line.lstrip('#/ ').strip()
                        if '.' in potential and len(potential.split()) == 1:
                            path = potential
            
            if path:
                path = path.strip()
                abs_path = os.path.abspath(path)
                print(f"[parser] Target: {path} (Absolute: {abs_path})")
                
                if path.lower() == "checklist.md":
                    continue
                
                os.makedirs(os.path.dirname(abs_path) if os.path.dirname(abs_path) else '.', exist_ok=True)
                
                with open(abs_path, "w") as f:
                    f.write(content)
                print(f"[parser] Wrote {len(content)} bytes to {path}")
                extracted_files.append(path)
        
        if not extracted_files:
            print("[parser] WARNING: No code blocks with file paths identified.")
            
        return extracted_files

if __name__ == "__main__":
    test = "```python:test.py\nprint('hello')\n```"
    ResponseParser.parse_and_write(test)
