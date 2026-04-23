import os
import sys
import tempfile

from test_utils import ROOT

from response_parser import ResponseParser


def test_relative_write_stays_inside_workspace():
    raw = """# Mighty Mouse Checklist - safe

## Phase 1: Planning
This is a detailed planning section with enough text to satisfy the workflow.
---
## Phase 2: Activity
This is a detailed activity section with enough text to satisfy the workflow.
---
## Phase 3: Verification
This is a detailed verification section with enough text to satisfy the workflow.

```python:src/ok.py
print('ok')
```
"""
    with tempfile.TemporaryDirectory() as tmp:
        files = ResponseParser.parse_and_write(raw, workspace_root=tmp)
        assert os.path.exists(os.path.join(tmp, "src", "ok.py"))
        assert "src/ok.py" in files


def test_absolute_paths_are_blocked():
    raw = """```python:/tmp/nope.py
print('nope')
```
"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            ResponseParser.parse_and_write(raw, workspace_root=tmp)
            raise AssertionError("Absolute path should have been blocked")
        except ValueError as e:
            assert "Absolute paths" in str(e)


def test_parent_traversal_is_blocked():
    raw = """```python:../escape.py
print('escape')
```
"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            ResponseParser.parse_and_write(raw, workspace_root=tmp)
            raise AssertionError("Parent traversal should have been blocked")
        except ValueError as e:
            assert "Parent traversal" in str(e)


def test_delete_requires_allowlist():
    raw = """```delete:obsolete.py
PURGED
```
"""
    with tempfile.TemporaryDirectory() as tmp:
        target = os.path.join(tmp, "obsolete.py")
        with open(target, "w") as f:
            f.write("old")

        try:
            ResponseParser.parse_and_write(raw, workspace_root=tmp, allowed_delete_paths=[])
            raise AssertionError("Deletion should require allowlist entry")
        except ValueError as e:
            assert "Deletion not permitted" in str(e)
        assert os.path.exists(target)

        ResponseParser.parse_and_write(raw, workspace_root=tmp, allowed_delete_paths=["obsolete.py"])
        assert not os.path.exists(target)


if __name__ == "__main__":
    test_relative_write_stays_inside_workspace()
    print("PASS: relative writes stay inside workspace")
    test_absolute_paths_are_blocked()
    print("PASS: absolute paths are blocked")
    test_parent_traversal_is_blocked()
    print("PASS: parent traversal is blocked")
    test_delete_requires_allowlist()
    print("PASS: deletion requires allowlist")
