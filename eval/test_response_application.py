import json
import sys
from pathlib import Path

import pytest

from mighty_mouse.orchestrator.response_application import (
    ResponseApplicationPolicy,
    ResponseApplicationRequest,
    apply_response,
    plan_response,
)
from mighty_mouse.orchestrator.response_parser import ResponseParser


def _request(raw_response, workspace_root, **policy_overrides):
    policy = ResponseApplicationPolicy(
        workspace_root=str(workspace_root),
        **policy_overrides,
    )
    return ResponseApplicationRequest(raw_response=raw_response, policy=policy)


def test_application_boundary_owns_application_and_keeps_policy_frozen(
    tmp_path, monkeypatch
):
    def fail_if_legacy_parser_called(*args, **kwargs):
        raise AssertionError(
            "application boundary must own response application"
        )

    monkeypatch.setattr(
        ResponseParser, "parse_and_write", fail_if_legacy_parser_called
    )
    request = _request(
        """```python:created.py
created
```""",
        tmp_path,
        allowed_delete_paths=("obsolete.py",),
        max_file_bytes=17,
        system_mode=True,
        strict_code_hygiene=True,
    )

    assert apply_response(request) == ["created.py"]
    assert (tmp_path / "created.py").read_text() == "created"

    with pytest.raises(AttributeError):
        request.policy.max_file_bytes = 18


def test_autoresearch_harness_uses_response_application_boundary(
    tmp_path, monkeypatch
):
    from eval import autoresearch_harness

    task_dir = tmp_path / "task"
    template = task_dir / "workspace"
    template.mkdir(parents=True)
    task_path = task_dir / "task.json"
    task_path.write_text(
        json.dumps(
            {
                "id": "response-application",
                "description": "Apply response",
                "complexity": "low",
                "workspace_template": "workspace",
                "allowed_paths": [],
                "checks": {"tests": [sys.executable, "-c", "pass"]},
            }
        )
    )

    observed = {}

    class FakeClient:
        def __init__(self, **kwargs):
            pass

        def chat(self, **kwargs):
            return {"content": "model response"}, {}

    def fake_apply(request):
        observed["request"] = request
        return []

    monkeypatch.setattr(autoresearch_harness, "OllamaChatClient", FakeClient)
    monkeypatch.setattr(autoresearch_harness, "apply_response", fake_apply)

    assert autoresearch_harness.run_task(task_path, "model", "host") is True
    request = observed["request"]
    assert isinstance(request, ResponseApplicationRequest)
    assert request.raw_response == "model response"
    assert Path(request.policy.workspace_root).is_absolute()


def test_application_boundary_preserves_relative_write(tmp_path):
    raw = """```python:src/ok.py
print('ok')
```"""

    output_paths = apply_response(_request(raw, tmp_path))

    assert output_paths == ["src/ok.py"]
    assert (tmp_path / "src/ok.py").read_text() == "print('ok')"


@pytest.mark.parametrize(
    "raw_response",
    [
        "plain model text",
        "```python\nprint('missing target')\n```",
    ],
)
def test_application_boundary_preserves_malformed_no_effect(
    tmp_path, raw_response
):
    assert apply_response(_request(raw_response, tmp_path)) == []
    assert list(Path(tmp_path).rglob("*")) == []


@pytest.mark.parametrize(
    ("relative_path", "error_fragment"),
    [
        ("../escape.py", "Parent traversal"),
        ("/absolute.py", "Absolute paths"),
    ],
)
def test_application_boundary_preserves_path_rejection_without_effect(
    tmp_path, relative_path, error_fragment
):
    raw = f"```python:{relative_path}\nprint('nope')\n```"

    with pytest.raises(ValueError, match=error_fragment):
        apply_response(_request(raw, tmp_path))

    assert list(Path(tmp_path).rglob("*.py")) == []


def test_application_boundary_preserves_delete_authorization(tmp_path):
    target = tmp_path / "obsolete.py"
    target.write_text("obsolete\n")
    raw = """```delete:obsolete.py

```"""

    with pytest.raises(ValueError, match="Deletion not permitted"):
        apply_response(_request(raw, tmp_path))
    assert target.exists()

    output_paths = apply_response(
        _request(raw, tmp_path, allowed_delete_paths=("obsolete.py",))
    )
    assert output_paths == ["obsolete.py"]
    assert not target.exists()


def test_application_boundary_preserves_remaining_policy_controls(tmp_path):
    oversized = "```python:large.py\n" + ("x" * 20) + "\n```"
    with pytest.raises(ValueError, match="oversized"):
        apply_response(_request(oversized, tmp_path, max_file_bytes=10))

    mighty = "```python:.mighty/secret.py\nsecret\n```"
    assert apply_response(_request(mighty, tmp_path)) == []
    assert not (tmp_path / ".mighty/secret.py").exists()
    assert apply_response(_request(mighty, tmp_path, system_mode=True)) == [
        ".mighty/secret.py"
    ]

    hygiene = "```python:leak.py\n</thought>\n```"
    with pytest.raises(ValueError, match="XML leakage"):
        apply_response(_request(hygiene, tmp_path, strict_code_hygiene=True))


def test_application_boundary_preserves_partial_side_effects(tmp_path):
    raw = """```python:first.py
x
```
```python:second.py
this block exceeds limit
```"""

    with pytest.raises(ValueError, match="oversized"):
        apply_response(_request(raw, tmp_path, max_file_bytes=10))

    assert (tmp_path / "first.py").exists()
    assert not (tmp_path / "second.py").exists()


def test_application_boundary_blocks_symlink_escape_for_write_and_delete(
    tmp_path
):
    outside = tmp_path.parent / "outside-response-application"
    outside.mkdir()
    link = tmp_path / "linked"
    link.symlink_to(outside, target_is_directory=True)

    write_raw = """```python:linked/escaped.py
escape
```"""
    with pytest.raises(ValueError, match="Resolved path escapes workspace"):
        apply_response(_request(write_raw, tmp_path))
    assert not (outside / "escaped.py").exists()

    target = outside / "obsolete.py"
    target.write_text("keep\n")
    delete_raw = """```delete:linked/obsolete.py

```"""
    with pytest.raises(ValueError, match="Resolved path escapes workspace"):
        apply_response(
            _request(
                delete_raw,
                tmp_path,
                allowed_delete_paths=("linked/obsolete.py",),
            )
        )
    assert target.exists()


def test_application_boundary_blocks_checklist_symlink_before_later_write(
    tmp_path,
):
    outside = tmp_path.parent / "outside-checklist-response-application"
    outside.mkdir()
    outside_checklist = outside / "CHECKLIST.md"
    outside_checklist.write_text("keep\n")
    (tmp_path / "CHECKLIST.md").symlink_to(outside_checklist)
    raw = """# Mighty Mouse Checklist
unsafe
```python:later.py
later
```"""

    with pytest.raises(ValueError, match="Resolved path escapes workspace"):
        apply_response(_request(raw, tmp_path))

    assert outside_checklist.read_text() == "keep\n"
    assert not (tmp_path / "later.py").exists()


def test_application_boundary_normalizes_protected_path_for_authorization(
    tmp_path,
):
    raw = """```python:./.mighty/secret.py
secret
```"""

    assert apply_response(_request(raw, tmp_path)) == []
    assert not (tmp_path / ".mighty/secret.py").exists()
    assert apply_response(_request(raw, tmp_path, system_mode=True)) == [
        "./.mighty/secret.py"
    ]
    assert (tmp_path / ".mighty/secret.py").read_text() == "secret"


def test_application_boundary_handles_empty_and_inline_delete_blocks(tmp_path):
    target = tmp_path / "obsolete_shim.py"
    target.write_text("bad code\n")

    raw = """```delete:obsolete_shim.py
```
```python:valid.py
def ok(): pass
```"""

    res = apply_response(
        _request(raw, tmp_path, allowed_delete_paths=("obsolete_shim.py",))
    )
    assert not target.exists()
    assert (tmp_path / "valid.py").exists()
    assert res == ["obsolete_shim.py", "valid.py"]


def test_write_allowlist_permits_exact_path_and_rejects_others(tmp_path):
    """Only paths in allowed_write_paths are written; others raise error."""
    raw = """```python:allowed.py
allowed_code
```
```python:forbidden.py
forbidden_code
```"""
    with pytest.raises(
        ValueError, match="Write not permitted for non-allowlisted path"
    ):
        apply_response(
            _request(raw, tmp_path, allowed_write_paths=("allowed.py",))
        )
    # The first allowed file was written before the error halted processing
    assert (tmp_path / "allowed.py").exists()
    assert not (tmp_path / "forbidden.py").exists()


def test_write_allowlist_blocks_unauthorized_checklist(tmp_path):
    """Implicit/explicit CHECKLIST.md rejected if not in write allowlist."""
    raw = """# Mighty Mouse Checklist
1. Step one
```python:allowed.py
code
```"""
    with pytest.raises(
        ValueError, match="Write not permitted for non-allowlisted path"
    ):
        apply_response(
            _request(raw, tmp_path, allowed_write_paths=("allowed.py",))
        )
    assert not (tmp_path / "CHECKLIST.md").exists()
    assert not (tmp_path / "allowed.py").exists()


def test_write_allowlist_permits_checklist_when_allowlisted(tmp_path):
    """CHECKLIST.md succeeds when explicitly in allowed_write_paths."""
    raw = """# Mighty Mouse Checklist
1. Step one
```python:allowed.py
code
```"""
    res = apply_response(
        _request(
            raw,
            tmp_path,
            allowed_write_paths=("allowed.py", "CHECKLIST.md"),
        )
    )
    assert "allowed.py" in res
    assert (tmp_path / "CHECKLIST.md").exists()
    assert (tmp_path / "allowed.py").exists()


def test_write_allowlist_normalized_posix_paths(tmp_path):
    """Allowed write paths match normalized relative paths."""
    raw = """```python:src/nested/app.py
app_code
```"""
    res = apply_response(
        _request(
            raw,
            tmp_path,
            allowed_write_paths=("./src/nested/app.py",),
        )
    )
    assert "src/nested/app.py" in res
    assert (tmp_path / "src/nested/app.py").read_text() == "app_code"


def test_legacy_allowed_write_paths_none_preserves_baseline_behavior(
    tmp_path,
):
    """When allowed_write_paths is None, baseline path resolution is kept."""
    raw = r"""```python:src\legacy.py
legacy_code
```"""
    res = apply_response(_request(raw, tmp_path))
    assert res == [r"src\legacy.py"]
    assert (tmp_path / "src\\legacy.py").exists()
    assert (tmp_path / "src\\legacy.py").read_text() == "legacy_code"


def test_legacy_deletion_behavior_remains_unchanged(tmp_path):
    """When allowed_write_paths is None, deletion keeps baseline semantics."""
    target = tmp_path / "src\\legacy.py"
    target.write_text("old_code\n")
    raw = r"""```delete:src\legacy.py
```"""
    res = apply_response(
        _request(raw, tmp_path, allowed_delete_paths=(r"src\legacy.py",))
    )
    assert res == [r"src\legacy.py"]
    assert not target.exists()


def test_write_allowlist_rejects_backslash_candidate_paths_fail_closed(
    tmp_path,
):
    """Strict write allowlist rejects backslash candidate path fail-closed."""
    raw = r"""```python:src\main.py
main_code
```"""
    with pytest.raises(
        ValueError, match="Write not permitted for non-allowlisted path"
    ):
        apply_response(
            _request(
                raw,
                tmp_path,
                allowed_write_paths=("src/main.py",),
            )
        )
    # Neither literal backslash nor posix directory file is created
    assert not (tmp_path / "src\\main.py").exists()
    assert not (tmp_path / "src" / "main.py").exists()


def test_write_allowlist_permits_canonical_posix_path(tmp_path):
    """Strict write allowlist permits canonical posix path."""
    raw = """```python:src/main.py
main_code
```"""
    res = apply_response(
        _request(
            raw,
            tmp_path,
            allowed_write_paths=("src/main.py",),
        )
    )
    assert res == ["src/main.py"]
    assert (tmp_path / "src" / "main.py").exists()
    assert (tmp_path / "src" / "main.py").read_text() == "main_code"


def test_write_allowlist_rejects_backslash_parent_traversal(tmp_path):
    """Parent traversal via backslash is rejected fail-closed."""
    raw = r"""```python:..\escape.py
malicious
```"""
    with pytest.raises(
        ValueError, match="Write not permitted for non-allowlisted path"
    ):
        apply_response(
            _request(
                raw,
                tmp_path,
                allowed_write_paths=("escape.py",),
            )
        )
    assert not (tmp_path.parent / "escape.py").exists()
    assert not (tmp_path / "escape.py").exists()


def test_plan_response_and_apply_response_parity_on_strict_allowlist(
    tmp_path,
):
    """plan_response and apply_response agree on rejecting backslashes."""
    raw_bad = r"""```python:src\main.py
main_code
```"""
    req_bad = _request(
        raw_bad,
        tmp_path,
        allowed_write_paths=("src/main.py",),
    )
    with pytest.raises(
        ValueError, match="Write not permitted for non-allowlisted path"
    ):
        plan_response(req_bad)

    with pytest.raises(
        ValueError, match="Write not permitted for non-allowlisted path"
    ):
        apply_response(req_bad)

    raw_ok = """```python:src/main.py
main_code
```"""
    req_ok = _request(
        raw_ok,
        tmp_path,
        allowed_write_paths=("src/main.py",),
    )
    plan = plan_response(req_ok)
    assert plan.output_paths == ("src/main.py",)
    assert plan.operations[0].target_path == str(tmp_path / "src" / "main.py")

    res = apply_response(req_ok)
    assert res == ["src/main.py"]
    assert (tmp_path / "src" / "main.py").exists()
    assert (tmp_path / "src" / "main.py").read_text() == "main_code"
