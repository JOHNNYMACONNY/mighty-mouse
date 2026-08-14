"""Contract tests for legacy parser compatibility delegation."""

from mighty_mouse.orchestrator import ResponseParser as ExportedResponseParser
from mighty_mouse.orchestrator import response_application
from mighty_mouse.orchestrator.response_parser import (
    COMPATIBILITY_DISPOSITION,
    ResponseParser,
)


def test_public_parser_export_and_disposition_remain_explicit() -> None:
    assert ExportedResponseParser is ResponseParser
    assert COMPATIBILITY_DISPOSITION == "NO_FURTHER_ARCHITECTURE_NEEDED"


def test_legacy_parser_delegates_policy(monkeypatch, tmp_path) -> None:
    raw_response = "```python:answer.py\nprint('ok')\n```"
    captured = []

    def fake_apply_response(request):
        captured.append(request)
        return ["answer.py"]

    monkeypatch.setattr(
        response_application,
        "apply_response",
        fake_apply_response,
    )

    result = ResponseParser.parse_and_write(
        raw_response,
        workspace_root=str(tmp_path),
        allowed_delete_paths=["obsolete.py"],
        max_file_bytes=123,
        system_mode=True,
        strict_code_hygiene=True,
    )

    assert result == ["answer.py"]
    assert len(captured) == 1
    request = captured[0]
    assert request.raw_response == raw_response
    assert request.policy.workspace_root == str(tmp_path)
    assert request.policy.allowed_delete_paths == ("obsolete.py",)
    assert request.policy.max_file_bytes == 123
    assert request.policy.system_mode is True
    assert request.policy.strict_code_hygiene is True
