"""Antigravity PreToolUse host hook leaf adapter v1.

Translates observed Antigravity PreToolUse payloads into canonical
HostHookEvent values and projects canonical HostHookResult values
back into Antigravity decision JSON.

Enforces the core architectural invariant: host payload != authority.
"""

from __future__ import annotations

from typing import Any, Mapping

from mighty_mouse.host.hooks import (
    HOST_HOOK_SCHEMA_VERSION,
    HostHookAction,
    HostHookEvent,
    HostHookResult,
    normalize_target_paths,
)

# Supported tools registered for Antigravity PreToolUse lifecycle hooks
SUPPORTED_FILE_WRITE_TOOLS = frozenset(
    {
        "write_to_file",
        "replace_file_content",
        "multi_replace_file_content",
    }
)
SUPPORTED_SHELL_TOOLS = frozenset({"run_command"})

# Bounded privacy-safe host reason projections for canonical reason codes
_CANONICAL_REASON_DESCRIPTIONS: dict[str, str] = {
    "not_applicable": "Action is not applicable",
    "malformed_event": "Malformed host event",
    "unsupported_phase": "Unsupported hook phase",
    "unsupported_action": "Unsupported host action",
    "invalid_workspace": "Invalid workspace",
    "runtime_context_unavailable": "Runtime context unavailable",
    "verification_passed": "Verification passed",
    "verification_failed": "Verification failed",
    "recovery_not_enabled": "Recovery not enabled",
    "recovery_succeeded": "Recovery succeeded",
    "recovery_failed": "Recovery failed",
    "retry_budget_exhausted": "Retry budget exhausted",
    "recursive_hook_suppressed": "Recursive hook suppressed",
    "internal_error": "Internal hook error",
}


def _resolve_string_alias(
    payload: Mapping[str, Any],
    aliases: tuple[str, ...],
    *,
    allow_absent_none: bool = False,
) -> tuple[str | None, bool]:
    """Resolve a single string property from candidate aliases.

    If any alias key is present in payload:
    - It must be a valid non-empty string (or None if allow_absent_none=True).
    - If non-string, empty, or None (when allow_absent_none=False), it fails.
    - If multiple aliases are present with contradictory values, it fails.
    Returns (value, has_conflict).
    """
    found: list[str] = []
    seen_none: bool = False
    for alias in aliases:
        if alias in payload:
            val = payload[alias]
            if val is None:
                if not allow_absent_none:
                    return None, True
                seen_none = True
            elif isinstance(val, str) and val.strip():
                found.append(val.strip())
            else:
                # Malformed non-string or whitespace-only value found
                return None, True
    if not found:
        if seen_none and not allow_absent_none:
            return None, True
        return None, False
    # If any present alias was explicitly None and another had a string
    # then treat as conflicting aliases
    if seen_none and allow_absent_none and found:
        return None, True
    first = found[0]
    for other in found[1:]:
        if other != first:
            return None, True
    return first, False


def _resolve_dict_alias(
    payload: Mapping[str, Any], aliases: tuple[str, ...]
) -> tuple[Mapping[str, Any] | None, bool]:
    """Resolve a single dict property from candidate aliases.

    If any alias key is present in payload:
    - It must be a valid Mapping.
    - If None, string, list, or other non-mapping, it fails closed.
    - If multiple aliases are present with contradictory values, it fails.
    Returns (value, has_conflict).
    """
    found: list[Mapping[str, Any]] = []
    has_explicit_alias: bool = False
    for alias in aliases:
        if alias in payload:
            has_explicit_alias = True
            val = payload[alias]
            if isinstance(val, Mapping):
                found.append(val)
            else:
                # Explicitly present None or non-mapping -> fail closed
                return None, True
    if not has_explicit_alias:
        return {}, False
    first = found[0]
    for other in found[1:]:
        if other != first:
            return None, True
    return first, False


def _resolve_target_file(
    tool_input: Mapping[str, Any],
) -> tuple[str | None, bool]:
    """Resolve TargetFile / file_path write target aliases fail-closed.

    Normalizes and canonicalizes paths using the Ticket 1 contract normalizer
    so equivalent POSIX/Windows paths reconcile identically.
    Returns (canonical_target_path, has_conflict).
    """
    aliases = ("TargetFile", "file_path")
    found: list[str] = []
    has_explicit_alias: bool = False
    for alias in aliases:
        if alias in tool_input:
            has_explicit_alias = True
            val = tool_input[alias]
            if isinstance(val, str) and val.strip():
                try:
                    norm = normalize_target_paths((val.strip(),))
                except ValueError:
                    # Invalid canonical path -> fail closed
                    return None, True
                if norm:
                    found.append(norm[0])
                else:
                    return None, True
            else:
                # Explicit None, non-string, or whitespace -> fail
                return None, True
    if not has_explicit_alias:
        return None, False
    first = found[0]
    for other in found[1:]:
        if other != first:
            return None, True
    return first, False


def adapt_antigravity_pre_tool_use(
    payload: Any,
    *,
    event_id: str,
) -> HostHookEvent | HostHookResult:
    """Normalize Antigravity PreToolUse payload to HostHookEvent.

    If the payload is malformed, unrecognized, or contradictory, returns a
    fail-closed HostHookResult with disposition='deny' without echoing
    untrusted payloads or command text in summaries.
    """
    # event_id is caller/adapter correlation data; must be valid non-empty str
    if not isinstance(event_id, str) or not event_id.strip():
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id="malformed_event_id",
            disposition="deny",
            reason_code="malformed_event",
            summary="Invalid or missing event_id",
        )

    norm_event_id = event_id.strip()

    if not isinstance(payload, Mapping):
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Host payload must be a key-value mapping",
        )

    # 1. Resolve tool name
    tool_name, tool_conflict = _resolve_string_alias(
        payload,
        ("tool_name", "tool", "name", "tool_call"),
        allow_absent_none=False,
    )
    if tool_conflict or not tool_name:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Missing, malformed, or contradictory tool name",
        )

    # 2. Resolve workspace
    workspace, ws_conflict = _resolve_string_alias(
        payload,
        ("workspace_path", "workspace", "cwd"),
        allow_absent_none=False,
    )
    if ws_conflict or not workspace:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="invalid_workspace",
            summary="Missing, malformed, or contradictory workspace path",
        )

    # 3. Resolve optional session ID
    session_id, sess_conflict = _resolve_string_alias(
        payload,
        ("conversation_id", "conversationId", "session_id"),
        allow_absent_none=True,
    )
    if sess_conflict:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Contradictory session identification aliases",
        )

    # 4. Resolve tool input mapping
    tool_input, input_conflict = _resolve_dict_alias(
        payload, ("tool_input", "args", "arguments", "input")
    )
    if input_conflict or tool_input is None:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Malformed or contradictory tool input arguments",
        )

    # 5. Map tool to canonical HostHookAction
    if tool_name in SUPPORTED_FILE_WRITE_TOOLS:
        raw_path, path_conflict = _resolve_target_file(tool_input)
        if path_conflict:
            return HostHookResult(
                schema_version=HOST_HOOK_SCHEMA_VERSION,
                event_id=norm_event_id,
                disposition="deny",
                reason_code="malformed_event",
                summary="Invalid target path",
            )
        target_paths = (raw_path,) if raw_path else ()
        try:
            action = HostHookAction(
                kind="file_write",
                mutation_class="workspace_mutation",
                target_paths=target_paths,
            )
        except ValueError:
            return HostHookResult(
                schema_version=HOST_HOOK_SCHEMA_VERSION,
                event_id=norm_event_id,
                disposition="deny",
                reason_code="malformed_event",
                summary="Invalid target path",
            )
    elif tool_name in SUPPORTED_SHELL_TOOLS:
        # run_command -> shell_command/unknown; never retain command text
        action = HostHookAction(
            kind="shell_command",
            mutation_class="unknown",
            target_paths=(),
        )
    else:
        # Unsupported tool -> fail closed
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="unsupported_action",
            summary="Unsupported Antigravity tool",
        )

    # 6. Construct canonical HostHookEvent (adapter-owned fields fixed)
    try:
        return HostHookEvent(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            phase="pre_action",
            workspace=workspace,
            action=action,
            source="antigravity",
            session_id=session_id,
        )
    except ValueError:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Canonical event validation failed",
        )


def render_antigravity_pre_tool_use_result(
    result: HostHookResult,
) -> dict[str, str]:
    """Project pre-action HostHookResult into Antigravity decision JSON.

    Projects controlled, privacy-safe host reason strings derived from
    canonical reason codes rather than echoing arbitrary summary text.
    """
    if not isinstance(result, HostHookResult):
        raise ValueError("result must be an instance of HostHookResult")

    host_reason = _CANONICAL_REASON_DESCRIPTIONS.get(
        result.reason_code, "Internal hook error"
    )

    if result.disposition == "allow":
        return {
            "decision": "allow",
            "status": "allow",
            "action": "allow",
            "reason": host_reason,
        }
    elif result.disposition == "deny":
        return {
            "decision": "deny",
            "status": "deny",
            "action": "deny",
            "reason": host_reason,
        }
    else:
        raise ValueError(
            "Unsupported pre-action disposition for Antigravity: "
            f"{result.disposition}"
        )
