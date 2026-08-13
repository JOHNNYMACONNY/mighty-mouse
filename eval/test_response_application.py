import json
import sys
from pathlib import Path

import pytest

from mighty_mouse.orchestrator.response_application import (
    ResponseApplicationPolicy,
    ResponseApplicationRequest,
    apply_response,
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
