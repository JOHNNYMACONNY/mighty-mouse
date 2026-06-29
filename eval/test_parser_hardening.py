import os
import sys
import tempfile
import re

# Ensure we can load from src/mighty_mouse/orchestrator
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if os.path.join(ROOT, "src", "mighty_mouse", "orchestrator") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "src", "mighty_mouse", "orchestrator"))

from response_parser import ResponseParser

def test_strict_fence_still_works():
    raw = """```python:src/main.py
print('strict')
```"""
    with tempfile.TemporaryDirectory() as tmp:
        files = ResponseParser.parse_and_write(raw, workspace_root=tmp)
        assert "src/main.py" in files
        with open(os.path.join(tmp, "src/main.py"), "r") as f:
            assert f.read().strip() == "print('strict')"
    print("PASS: test_strict_fence_still_works")

def test_file_hint_sniffing():
    raw = """File: src/utils.py
```python
print('sniffed file')
```"""
    with tempfile.TemporaryDirectory() as tmp:
        files = ResponseParser.parse_and_write(raw, workspace_root=tmp)
        assert "src/utils.py" in files
        with open(os.path.join(tmp, "src/utils.py"), "r") as f:
            assert f.read().strip() == "print('sniffed file')"
    print("PASS: test_file_hint_sniffing")

def test_target_hint_sniffing():
    raw = """Target: config.yaml
```yaml
key: value
```"""
    with tempfile.TemporaryDirectory() as tmp:
        files = ResponseParser.parse_and_write(raw, workspace_root=tmp)
        assert "config.yaml" in files
    print("PASS: test_target_hint_sniffing")

def test_malformed_fence_spacing_and_case():
    raw = """```PYTHON :  src/app.py 
print('permissive')
```"""
    with tempfile.TemporaryDirectory() as tmp:
        files = ResponseParser.parse_and_write(raw, workspace_root=tmp)
        assert "src/app.py" in files
    print("PASS: test_malformed_fence_spacing_and_case")

def test_ambiguous_targets_fail():
    raw = """File: a.py
Target: b.py
```python
print('ambiguous')
```"""
    with tempfile.TemporaryDirectory() as tmp:
        try:
            ResponseParser.parse_and_write(raw, workspace_root=tmp)
            assert False, "Should have raised ValueError for ambiguity"
        except ValueError as e:
            assert "Ambiguous file targets" in str(e)
    print("PASS: test_ambiguous_targets_fail")

def test_mighty_isolation_blocked_by_default():
    raw = """```text:.mighty/PLAN.md
plan content
```"""
    with tempfile.TemporaryDirectory() as tmp:
        files = ResponseParser.parse_and_write(raw, workspace_root=tmp, system_mode=False)
        assert ".mighty/PLAN.md" not in files
        assert not os.path.exists(os.path.join(tmp, ".mighty/PLAN.md"))
    print("PASS: test_mighty_isolation_blocked_by_default")

def test_mighty_isolation_allowed_in_system_mode():
    raw = """```text:.mighty/PLAN.md
plan content
```"""
    with tempfile.TemporaryDirectory() as tmp:
        files = ResponseParser.parse_and_write(raw, workspace_root=tmp, system_mode=True)
        assert ".mighty/PLAN.md" in files
        assert os.path.exists(os.path.join(tmp, ".mighty/PLAN.md"))
    print("PASS: test_mighty_isolation_allowed_in_system_mode")

if __name__ == "__main__":
    test_strict_fence_still_works()
    test_file_hint_sniffing()
    test_target_hint_sniffing()
    test_malformed_fence_spacing_and_case()
    test_ambiguous_targets_fail()
    test_mighty_isolation_blocked_by_default()
    test_mighty_isolation_allowed_in_system_mode()
    print("\nALL PARSER HARDENING TESTS PASSED")
