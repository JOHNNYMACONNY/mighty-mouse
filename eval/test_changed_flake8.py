from pathlib import Path
import subprocess
import sys


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import check_changed_flake8 as changed_flake8  # noqa: E402
from check_changed_flake8 import (  # noqa: E402
    Violation,
    filter_changed_violations,
    parse_changed_lines,
)


def test_parse_changed_lines_tracks_added_lines_only():
    diff = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -1,3 +1,4 @@
 first = 1
+unused = 2
 second = 2
 third = 3
"""

    assert parse_changed_lines(diff) == {"example.py": {2}}


def test_filter_changed_violations_ignores_old_lines():
    violations = [
        Violation("example.py", 2, 1, "F401", "unused import"),
        Violation("example.py", 3, 1, "E501", "line too long"),
    ]

    assert filter_changed_violations(
        violations,
        {"example.py": {2}},
    ) == [violations[0]]


def test_parse_changed_lines_handles_new_file():
    diff = """diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+first = 1
+second = 2
"""

    assert parse_changed_lines(diff) == {"new.py": {1, 2}}


def test_main_fails_when_flake8_process_fails(monkeypatch, capsys):
    diff = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -0,0 +1 @@
+value = 1
"""
    monkeypatch.setattr(
        changed_flake8,
        "_git_diff",
        lambda _base: subprocess.CompletedProcess([], 0, diff, ""),
    )
    monkeypatch.setattr(
        changed_flake8,
        "_run_flake8",
        lambda _paths: subprocess.CompletedProcess([], 2, "", "flake8 crashed"),
    )

    assert changed_flake8.main(["--base", "base"]) == 2
    assert "flake8 crashed" in capsys.readouterr().err


def test_main_fails_when_flake8_writes_stderr(monkeypatch, capsys):
    diff = """diff --git a/example.py b/example.py
--- a/example.py
+++ b/example.py
@@ -0,0 +1 @@
+value = 1
"""
    monkeypatch.setattr(
        changed_flake8,
        "_git_diff",
        lambda _base: subprocess.CompletedProcess([], 0, diff, ""),
    )
    monkeypatch.setattr(
        changed_flake8,
        "_run_flake8",
        lambda _paths: subprocess.CompletedProcess([], 0, "", "unexpected warning"),
    )

    assert changed_flake8.main(["--base", "base"]) == 2
    assert "unexpected warning" in capsys.readouterr().err
