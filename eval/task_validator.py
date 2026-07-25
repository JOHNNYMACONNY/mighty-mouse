import ast
import json
import os
import shutil
import tempfile
import unittest
import subprocess
import sys

REQUIRED_TASK_FIELDS = ["id", "title", "description", "expected_files", "test_script"]

class TaskValidationError(Exception):
    pass

def validate_task_schema(task_data):
    for field in REQUIRED_TASK_FIELDS:
        if field not in task_data or not task_data[field]:
            raise TaskValidationError(f"Missing required field: '{field}'")
    
    if not isinstance(task_data["expected_files"], list) or len(task_data["expected_files"]) == 0:
        raise TaskValidationError("'expected_files' must be a non-empty list.")
    
    if not isinstance(task_data["test_script"], str) or len(task_data["test_script"].strip()) == 0:
        raise TaskValidationError("'test_script' must be a non-empty string.")

def compile_test_script(test_script):
    try:
        ast.parse(test_script)
    except SyntaxError as e:
        raise TaskValidationError(f"Test script contains syntax error: {e}")

def _extract_ast_fingerprint(python_code):
    try:
        tree = ast.parse(python_code)
        nodes = []
        for node in ast.walk(tree):
            nodes.append(type(node).__name__)
        return "_".join(nodes)
    except Exception:
        return ""

def check_contamination_and_duplicates(task_data, existing_tasks):
    new_fp = _extract_ast_fingerprint(task_data.get("test_script", ""))
    new_desc = task_data.get("description", "").lower().strip()
    
    for existing in existing_tasks:
        if existing.get("id") == task_data.get("id"):
            continue
        
        # Check description exact overlap
        exist_desc = existing.get("description", "").lower().strip()
        if new_desc == exist_desc and len(new_desc) > 0:
            raise TaskValidationError(f"Duplicate task description with {existing.get('id')}")
        
        # Check AST fingerprint identicality
        exist_fp = _extract_ast_fingerprint(existing.get("test_script", ""))
        if new_fp and exist_fp and new_fp == exist_fp and len(new_fp) > 50:
            raise TaskValidationError(f"Duplicate test script AST logic with {existing.get('id')}")

def execute_task_test(test_script, work_dir):
    test_file = os.path.join(work_dir, "_task_test.py")
    with open(test_file, "w") as f:
        f.write(test_script)
    
    res = subprocess.run([sys.executable, test_file], cwd=work_dir, capture_output=True, text=True, timeout=10)
    return res.returncode == 0, res.stdout + "\n" + res.stderr

def run_negative_controls(task_data, reference_files=None, setup_files=None):
    """
    Adversarially proves that:
    1. Untouched workspace fails (or missing expected files).
    2. Empty file implementation fails behavioral tests.
    3. Keyword-stuffed implementation fails behavioral tests.
    4. Static dummy return implementation fails behavioral tests.
    5. Reference implementation passes all tests.
    """
    with tempfile.TemporaryDirectory() as temp_dir:
        # Setup workspace fixtures if present
        if setup_files:
            for rel_p, content in setup_files.items():
                p = os.path.join(temp_dir, rel_p)
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w") as f:
                    f.write(content)
        
        # Setup deletable ghost files if specified
        for ghost in task_data.get("deletable_files", []):
            gp = os.path.join(temp_dir, ghost)
            with open(gp, "w") as f:
                f.write("# Obsolete file with syntax error\ndef bad_code(: pass\n")

        # 1. Untouched workspace: expected file does NOT exist yet.
        # Running test_script must fail (or raise missing file / assertion).
        passed, log = execute_task_test(task_data["test_script"], temp_dir)
        if passed:
            raise TaskValidationError("Negative Control #1 Failed: Untouched workspace PASSED tests! Tests must fail when expected files are missing.")

        expected_files = task_data["expected_files"]
        
        # 2. Empty implementation: 0-byte file
        for ef in expected_files:
            ep = os.path.join(temp_dir, ef)
            os.makedirs(os.path.dirname(ep), exist_ok=True)
            with open(ep, "w") as f:
                f.write("")
        
        passed, log = execute_task_test(task_data["test_script"], temp_dir)
        if passed:
            raise TaskValidationError("Negative Control #2 Failed: Empty file implementation PASSED tests!")

        # 3. Keyword-stuffed implementation: docstring / comment only
        for ef in expected_files:
            ep = os.path.join(temp_dir, ef)
            kw_content = f'"""\nRequirement: {task_data.get("title", "")}\n{task_data.get("description", "")}\n"""\n'
            with open(ep, "w") as f:
                f.write(kw_content)
        
        passed, log = execute_task_test(task_data["test_script"], temp_dir)
        if passed:
            raise TaskValidationError("Negative Control #3 Failed: Keyword-stuffed implementation PASSED tests!")

        # 4. Static dummy return implementation
        for ef in expected_files:
            ep = os.path.join(temp_dir, ef)
            dummy_content = 'def dummy_func(*args, **kwargs):\n    return True\n'
            with open(ep, "w") as f:
                f.write(dummy_content)

        passed, log = execute_task_test(task_data["test_script"], temp_dir)
        if passed:
            raise TaskValidationError("Negative Control #4 Failed: Static dummy return implementation PASSED tests!")

        # Purge deletable ghost files if present before testing reference solution
        for ghost in task_data.get("deletable_files", []):
            gp = os.path.join(temp_dir, ghost)
            if os.path.exists(gp):
                os.remove(gp)

        # 5. Reference implementation: Must PASS cleanly
        if reference_files:
            for ef, ref_code in reference_files.items():
                ep = os.path.join(temp_dir, ef)
                with open(ep, "w") as f:
                    f.write(ref_code)

            passed, log = execute_task_test(task_data["test_script"], temp_dir)
            if not passed:
                raise TaskValidationError(f"Negative Control #5 Failed: Reference implementation FAILED tests!\nLogs:\n{log}")

def validate_task_completeness(task_data, existing_tasks=None, reference_files=None, setup_files=None):
    validate_task_schema(task_data)
    compile_test_script(task_data["test_script"])
    if existing_tasks:
        check_contamination_and_duplicates(task_data, existing_tasks)
    run_negative_controls(task_data, reference_files=reference_files, setup_files=setup_files)
    return True
