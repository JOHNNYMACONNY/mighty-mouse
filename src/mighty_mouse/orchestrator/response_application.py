"""Response application boundary for parsed model output.

This module owns the response-application request seam while the existing
``ResponseParser`` remains the compatibility implementation.  Agent
Execution must receive only a fully bound callable adapter built from this
boundary; parser policy stays outside Agent Execution.
"""

from __future__ import annotations

from dataclasses import dataclass

try:
    from .response_parser import ResponseParser
except ImportError:  # pragma: no cover - legacy direct-module imports.
    from response_parser import ResponseParser


@dataclass(frozen=True)
class ResponseApplicationPolicy:
    """Application policy preserved from the legacy parser contract."""

    workspace_root: str
    allowed_delete_paths: tuple[str, ...] = ()
    max_file_bytes: int = 100_000
    system_mode: bool = False
    strict_code_hygiene: bool = False


@dataclass(frozen=True)
class ResponseApplicationRequest:
    """One raw response plus its composition-root-bound application policy."""

    raw_response: str
    policy: ResponseApplicationPolicy


def apply_response(request: ResponseApplicationRequest) -> list[str]:
    """Apply one response while preserving legacy parser behavior."""

    policy = request.policy
    return ResponseParser.parse_and_write(
        request.raw_response,
        workspace_root=policy.workspace_root,
        allowed_delete_paths=policy.allowed_delete_paths,
        max_file_bytes=policy.max_file_bytes,
        system_mode=policy.system_mode,
        strict_code_hygiene=policy.strict_code_hygiene,
    )
