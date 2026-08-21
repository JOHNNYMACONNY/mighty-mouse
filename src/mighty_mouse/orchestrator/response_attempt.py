"""Private execution seam for one prepared response-attempt sequence."""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, replace
from typing import Any, Callable, Protocol, Sequence


@dataclass(frozen=True)
class ResponseAttemptContext:
    """Prepared inputs and state for one response-attempt sequence."""

    system_prompt: str
    user_prompt: str
    task_id: str
    attempt: int
    max_attempts: int
    workspace_root: str
    allowed_delete_paths: tuple[str, ...] = ()


class ProviderAdapter(Protocol):
    """Provider adapter retaining caller-owned metadata and raw-log behavior.

    Caller owns metadata and raw-log persistence.
    """

    def __call__(
        self,
        context: ResponseAttemptContext,
        usage_history: list[dict[str, Any]],
    ) -> str:
        ...


class ParserAdapter(Protocol):
    """Parser adapter for one successful provider response."""

    def __call__(
        self,
        response: str,
        context: ResponseAttemptContext,
    ) -> Sequence[str]:
        ...


@dataclass
class ResponseAttemptResult:
    """Execution-derived values consumed by the outer solve adapter."""

    response: str | None
    output_paths: list[str]
    usage_history: list[dict[str, Any]]
    schema_error: bool
    next_attempt: int
    next_user_prompt: str
    failed: bool


def execute_response_attempt(
    context: ResponseAttemptContext,
    provider_adapter: ProviderAdapter,
    parser_adapter: ParserAdapter | None = None,
    *,
    sleep_fn: Callable[[float], None] | None = None,
) -> ResponseAttemptResult:
    """Run provider and schema retries for one prepared execution sequence."""
    usage_history: list[dict[str, Any]] = []
    current_user_prompt = context.user_prompt
    attempt = context.attempt
    sleep = sleep_fn or time.sleep

    while attempt <= context.max_attempts:
        attempt_context = replace(
            context,
            user_prompt=current_user_prompt,
            attempt=attempt,
        )
        for attr in ("_sampling_temperature", "_candidate_index"):
            if hasattr(context, attr):
                object.__setattr__(
                    attempt_context, attr, getattr(context, attr)
                )
        try:
            response = provider_adapter(attempt_context, usage_history)
        except Exception as exc:
            print(f"[agent] ERROR during generation: {exc}", file=sys.stderr)
            if attempt < context.max_attempts:
                print("[agent] Retrying...", file=sys.stderr)
                sleep(2)
                attempt += 1
                continue

            print(
                "[agent] CRITICAL: Maximum attempts reached. Failing task.",
                file=sys.stderr,
            )
            return ResponseAttemptResult(
                response=None,
                output_paths=[],
                usage_history=usage_history,
                schema_error=False,
                next_attempt=attempt + 1,
                next_user_prompt=current_user_prompt,
                failed=True,
            )

        if parser_adapter is None:
            return ResponseAttemptResult(
                response=response,
                output_paths=[],
                usage_history=usage_history,
                schema_error=False,
                next_attempt=attempt + 1,
                next_user_prompt=current_user_prompt,
                failed=False,
            )

        parsed_paths = parser_adapter(response, attempt_context)
        output_paths = list(parsed_paths) if parsed_paths else []
        if output_paths:
            return ResponseAttemptResult(
                response=response,
                output_paths=output_paths,
                usage_history=usage_history,
                schema_error=False,
                next_attempt=attempt + 1,
                next_user_prompt=current_user_prompt,
                failed=False,
            )

        if attempt < context.max_attempts:
            print(
                "[agent] SCHEMA ERROR: No file blocks found. "
                "Retrying with explicit schema correction...",
                file=sys.stderr,
            )
            current_user_prompt += (
                "\n\nCRITICAL ERROR: No code blocks were found in your "
                "previous response. "
                "You MUST use the correct XML/Markdown format with file paths "
                "(e.g., ```python:path/to/file.py)."
            )
            attempt += 1
            continue

        print(
            "[agent] CRITICAL: Schema error persists after retry.",
            file=sys.stderr,
        )
        return ResponseAttemptResult(
            response=response,
            output_paths=[],
            usage_history=usage_history,
            schema_error=True,
            next_attempt=attempt + 1,
            next_user_prompt=current_user_prompt,
            failed=True,
        )

    return ResponseAttemptResult(
        response=None,
        output_paths=[],
        usage_history=usage_history,
        schema_error=False,
        next_attempt=attempt,
        next_user_prompt=current_user_prompt,
        failed=True,
    )
