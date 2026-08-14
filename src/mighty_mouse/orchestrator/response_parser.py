"""Legacy response-parser compatibility surface.

Supported direct imports retain ``ResponseParser`` while response
application owns parsing, validation, authorization, and filesystem writes.
"""

from __future__ import annotations


# Architecture disposition for public compatibility path.
COMPATIBILITY_DISPOSITION = "NO_FURTHER_ARCHITECTURE_NEEDED"


class ResponseParser:
    """Compatibility adapter for the canonical response application boundary."""

    @staticmethod
    def _resolve_target_path(path, workspace_root):
        """Preserve legacy private helper through canonical path resolution."""

        try:
            from .response_application import _resolve_target_path
        except ImportError:  # pragma: no cover - legacy direct-module imports.
            from response_application import _resolve_target_path
        return _resolve_target_path(path, workspace_root)

    @staticmethod
    def parse_and_write(
        raw_text,
        workspace_root=None,
        allowed_delete_paths=None,
        max_file_bytes=100_000,
        system_mode=False,
        strict_code_hygiene=False,
    ):
        """Delegate legacy parser calls to canonical response application."""

        try:
            from .response_application import (
                ResponseApplicationPolicy,
                ResponseApplicationRequest,
                apply_response,
            )
        except ImportError:  # pragma: no cover - legacy direct-module imports.
            from response_application import (
                ResponseApplicationPolicy,
                ResponseApplicationRequest,
                apply_response,
            )

        normalized_delete_paths = tuple(
            path.strip()
            for path in (allowed_delete_paths or [])
            if path and path.strip()
        )
        return apply_response(
            ResponseApplicationRequest(
                raw_response=raw_text,
                policy=ResponseApplicationPolicy(
                    workspace_root=workspace_root or "",
                    allowed_delete_paths=normalized_delete_paths,
                    max_file_bytes=max_file_bytes,
                    system_mode=system_mode,
                    strict_code_hygiene=strict_code_hygiene,
                ),
            )
        )


if __name__ == "__main__":
    test = "```python:test.py\nprint('hello')\n```"
    ResponseParser.parse_and_write(test)
