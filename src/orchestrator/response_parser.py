import os
import re


class ResponseParser:
    @staticmethod
    def _resolve_target_path(path, workspace_root):
        if not path:
            raise ValueError("Missing target path")

        path = path.strip()
        if os.path.isabs(path):
            raise ValueError(f"Absolute paths are not allowed: {path}")
        if ".." in path.split(os.sep):
            raise ValueError(f"Parent traversal is not allowed: {path}")

        workspace_root = os.path.abspath(workspace_root or os.getcwd())
        target_path = os.path.abspath(os.path.join(workspace_root, path))
        if target_path != workspace_root and not target_path.startswith(workspace_root + os.sep):
            raise ValueError(f"Resolved path escapes workspace: {path}")
        return path, target_path

    @staticmethod
    def parse_and_write(raw_text, workspace_root=None, allowed_delete_paths=None, max_file_bytes=100_000):
        print(f"[parser] Processing response (Length: {len(raw_text)})")
        workspace_root = os.path.abspath(workspace_root or os.getcwd())
        allowed_delete_paths = {p.strip() for p in (allowed_delete_paths or []) if p and p.strip()}

        checklist_match = re.search(r'# Mighty Mouse Checklist.*?(?=```|$)', raw_text, re.DOTALL | re.IGNORECASE)
        if checklist_match:
            checklist_content = checklist_match.group(0).strip()
            checklist_path = os.path.join(workspace_root, "CHECKLIST.md")
            with open(checklist_path, "w") as f:
                f.write(checklist_content)
                f.write("\n")
            print("[parser] Wrote CHECKLIST.md")

        file_blocks = re.finditer(r'```(?P<lang>\w+)?(?::(?P<path>[^\n\s]+))?.*?\n(?P<content>.*?)\n```', raw_text, re.DOTALL)

        extracted_files = []
        for block in file_blocks:
            path = block.group('path')
            content = block.group('content')

            if not path:
                lines = content.split('\n')
                for line in lines:
                    if not line.strip():
                        continue
                    first_line = line.strip()
                    if first_line.startswith('#') or first_line.startswith('//'):
                        potential = first_line.lstrip('#/ ').strip()
                        if '.' in potential and len(potential.split()) == 1:
                            path = potential
                    break

            if not path:
                continue

            path, target_path = ResponseParser._resolve_target_path(path, workspace_root)

            if path.lower() == "checklist.md":
                continue

            if len(content.encode("utf-8")) > max_file_bytes:
                raise ValueError(f"Refusing oversized file block for {path}")

            if block.group('lang') == 'delete':
                if path not in allowed_delete_paths:
                    raise ValueError(f"Deletion not permitted for path: {path}")
                if os.path.exists(target_path):
                    os.remove(target_path)
                    print(f"[parser] PURGED file: {path}")
                extracted_files.append(path)
                continue

            print(f"[parser] Target: {path} (Resolved: {target_path})")
            os.makedirs(os.path.dirname(target_path) if os.path.dirname(target_path) else '.', exist_ok=True)
            with open(target_path, "w") as f:
                f.write(content)
            print(f"[parser] Wrote {len(content)} bytes to {path}")
            extracted_files.append(path)

        if not extracted_files:
            print(f"[parser] !!!!!!!!! WARNING !!!!!!!!!")
            print(f"[parser] No code blocks with file paths identified in response.")
            print(f"[parser] Response length: {len(raw_text)} chars.")
            print(f"[parser] !!!!!!!!!!!!!!!!!!!!!!!!!!!")

        return extracted_files


if __name__ == "__main__":
    test = "```python:test.py\nprint('hello')\n```"
    ResponseParser.parse_and_write(test)
