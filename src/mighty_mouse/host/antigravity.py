"""Antigravity PreToolUse/PostToolUse host hook leaf adapter v1.

Translates observed Antigravity PreToolUse and PostToolUse payloads into
canonical HostHookEvent values and projects canonical HostHookResult values
back into Antigravity decision JSON.

Enforces the core architectural invariant: host payload != authority.
"""

from __future__ import annotations

import os
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


def _resolve_nested_tool_call(
    payload: Mapping[str, Any],
) -> tuple[str | None, Mapping[str, Any] | None, bool]:
    """Extract name and args from nested toolCall dict if present.

    Returns (tool_name, args_mapping, has_conflict).
    tool_name and args_mapping are None when toolCall key is absent.
    has_conflict is True on any structural violation.
    """
    if "toolCall" not in payload:
        return None, None, False
    tc = payload["toolCall"]
    if not isinstance(tc, Mapping):
        return None, None, True
    name_raw = tc.get("name")
    if not isinstance(name_raw, str) or not name_raw.strip():
        return None, None, True
    args_raw = tc.get("args")
    if args_raw is not None and not isinstance(args_raw, Mapping):
        return None, None, True
    args: Mapping[str, Any] = (
        args_raw if isinstance(args_raw, Mapping) else {}
    )
    return name_raw.strip(), args, False


def _resolve_workspace_paths(
    payload: Mapping[str, Any],
) -> tuple[list[str] | None, bool]:
    """Resolve workspacePaths list or fall back to flat string aliases.

    Returns (list_of_workspace_strings, has_conflict).
    Returns (None, True) on structural violations.
    Returns (None, False) when no workspace info present at all.
    """
    has_wp = "workspacePaths" in payload
    has_flat = any(
        k in payload for k in ("workspace_path", "workspace", "cwd")
    )
    if has_wp and has_flat:
        # Both present: must agree on at least one workspace string
        wp_val = payload["workspacePaths"]
        if not isinstance(wp_val, list) or not wp_val:
            return None, True
        flat_val, flat_conflict = _resolve_string_alias(
            payload,
            ("workspace_path", "workspace", "cwd"),
            allow_absent_none=False,
        )
        if flat_conflict or not flat_val:
            return None, True
        canonical_paths = _validate_workspace_list(wp_val)
        if canonical_paths is None:
            return None, True
        if flat_val.strip() not in canonical_paths:
            return None, True
        return canonical_paths, False
    if has_wp:
        wp_val = payload["workspacePaths"]
        if not isinstance(wp_val, list) or not wp_val:
            return None, True
        canonical_paths = _validate_workspace_list(wp_val)
        if canonical_paths is None:
            return None, True
        return canonical_paths, False
    if has_flat:
        flat_val, flat_conflict = _resolve_string_alias(
            payload,
            ("workspace_path", "workspace", "cwd"),
            allow_absent_none=False,
        )
        if flat_conflict or not flat_val:
            return None, True
        return [flat_val.strip()], False
    return None, False


def _validate_workspace_list(
    raw_list: list[Any],
) -> list[str] | None:
    """Validate a list of workspace path strings.

    Returns cleaned list on success, None on any structural violation.
    """
    result: list[str] = []
    for entry in raw_list:
        if not isinstance(entry, str) or not entry.strip():
            return None
        result.append(entry.strip())
    return result if result else None


def _relativize_absolute_target(
    abs_path: str,
    workspaces: list[str],
) -> tuple[str | None, bool]:
    """Relativize abs_path against exactly one containing workspace.

    Uses os.path.realpath for symlink-safe canonical resolution.
    Returns (relative_path, has_conflict).
    has_conflict=True on: outside all workspaces, multiple candidates,
    overlapping/nested workspaces matching target, or any path error.
    """
    try:
        real_target = os.path.realpath(abs_path)
    except (OSError, ValueError):
        return None, True

    matching: list[tuple[str, str]] = []
    for ws in workspaces:
        try:
            real_ws = os.path.realpath(ws)
        except (OSError, ValueError):
            return None, True
        # Ensure real_ws ends with sep for prefix matching
        ws_prefix = real_ws if real_ws.endswith(os.sep) else real_ws + os.sep
        if real_target == real_ws or real_target.startswith(ws_prefix):
            if real_target == real_ws:
                rel = "."
            else:
                rel = os.path.relpath(real_target, real_ws)
            matching.append((ws, rel))

    if len(matching) == 0:
        return None, True
    if len(matching) > 1:
        # Ambiguous: multiple workspaces contain target
        return None, True

    _ws, rel = matching[0]
    if not rel or rel == ".":
        return None, True
    # Validate the relativized path via canonical normalizer
    try:
        normalized = normalize_target_paths((rel,))
    except ValueError:
        return None, True
    if not normalized:
        return None, True
    return normalized[0], False


def _resolve_target_file(
    tool_input: Mapping[str, Any],
    workspaces: list[str] | None = None,
) -> tuple[str | None, bool]:
    """Resolve TargetFile / file_path write target fail-closed.

    For relative paths: normalizes via Ticket 1 contract normalizer.
    For absolute paths: relativizes against exactly one workspace entry
    when workspaces list is provided; fails closed otherwise.
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
                raw = val.strip()
                if os.path.isabs(raw):
                    if not workspaces:
                        return None, True
                    rel, conflict = _relativize_absolute_target(
                        raw, workspaces
                    )
                    if conflict or rel is None:
                        return None, True
                    found.append(rel)
                else:
                    try:
                        norm = normalize_target_paths((raw,))
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

    Supports production nested toolCall:{name,args} and workspacePaths
    array alongside backward-compatible flat aliases. Contradictory
    representations fail closed. Safe absolute TargetFile relativization
    uses realpath-based containment against workspacePaths entries.

    If the payload is malformed, unrecognized, or contradictory, returns a
    fail-closed HostHookResult with disposition='deny' without echoing
    untrusted payloads or command text in summaries.
    """
    # event_id is caller/adapter correlation data; must be valid non-empty
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

    # 1. Resolve tool name from nested toolCall or flat aliases
    nested_name, nested_args, tc_conflict = _resolve_nested_tool_call(payload)
    if tc_conflict:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Malformed nested toolCall structure",
        )

    flat_tool, flat_tool_conflict = _resolve_string_alias(
        payload,
        ("tool_name", "tool", "name"),
        allow_absent_none=False,
    )
    if flat_tool_conflict:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Missing, malformed, or contradictory tool name",
        )

    if nested_name is not None and flat_tool is not None:
        if nested_name != flat_tool:
            return HostHookResult(
                schema_version=HOST_HOOK_SCHEMA_VERSION,
                event_id=norm_event_id,
                disposition="deny",
                reason_code="malformed_event",
                summary="Contradictory nested and flat tool name aliases",
            )
        tool_name: str | None = nested_name
    elif nested_name is not None:
        tool_name = nested_name
    else:
        tool_name = flat_tool

    if not tool_name:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Missing, malformed, or contradictory tool name",
        )

    # 2. Resolve workspace paths
    workspaces, ws_conflict = _resolve_workspace_paths(payload)
    if ws_conflict or not workspaces:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="invalid_workspace",
            summary="Missing, malformed, or contradictory workspace path",
        )

    # Primary workspace for canonical event (first valid entry)
    workspace = workspaces[0]

    # 3. Resolve optional session ID (conversationId camelCase + aliases)
    session_id, sess_conflict = _resolve_string_alias(
        payload,
        ("conversationId", "conversation_id", "session_id"),
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

    # 4. Resolve tool input: nested toolCall.args takes precedence
    if nested_args is not None:
        # Validate no contradictory flat args alias
        flat_input, flat_input_conflict = _resolve_dict_alias(
            payload, ("tool_input", "args", "arguments", "input")
        )
        if flat_input_conflict:
            return HostHookResult(
                schema_version=HOST_HOOK_SCHEMA_VERSION,
                event_id=norm_event_id,
                disposition="deny",
                reason_code="malformed_event",
                summary="Malformed or contradictory tool input arguments",
            )
        # flat_input is {} when absent -> no conflict possible
        tool_input: Mapping[str, Any] = nested_args
    else:
        tool_input_raw, input_conflict = _resolve_dict_alias(
            payload, ("tool_input", "args", "arguments", "input")
        )
        if input_conflict or tool_input_raw is None:
            return HostHookResult(
                schema_version=HOST_HOOK_SCHEMA_VERSION,
                event_id=norm_event_id,
                disposition="deny",
                reason_code="malformed_event",
                summary="Malformed or contradictory tool input arguments",
            )
        tool_input = tool_input_raw

    # 5. Map tool to canonical HostHookAction
    if tool_name in SUPPORTED_FILE_WRITE_TOOLS:
        raw_path, path_conflict = _resolve_target_file(
            tool_input, workspaces=workspaces
        )
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


def adapt_antigravity_post_tool_use(
    payload: Any,
    *,
    event_id: str,
) -> HostHookEvent | HostHookResult:
    """Normalize Antigravity PostToolUse payload to post_action observation.

    Ingests nested toolCall, stepIdx, error, and common fields. No recovery,
    verification, mutation, or policy decision is performed. Error content
    and payload data are never echoed in canonical fields or output.
    Returns a fail-closed HostHookResult on any structural violation.
    """
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

    # 1. Resolve tool name (nested toolCall.name or flat aliases)
    nested_name, nested_args, tc_conflict = _resolve_nested_tool_call(payload)
    if tc_conflict:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Malformed nested toolCall structure",
        )

    flat_tool, flat_tool_conflict = _resolve_string_alias(
        payload,
        ("tool_name", "tool", "name"),
        allow_absent_none=False,
    )
    if flat_tool_conflict:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Missing, malformed, or contradictory tool name",
        )

    if nested_name is not None and flat_tool is not None:
        if nested_name != flat_tool:
            return HostHookResult(
                schema_version=HOST_HOOK_SCHEMA_VERSION,
                event_id=norm_event_id,
                disposition="deny",
                reason_code="malformed_event",
                summary="Contradictory nested and flat tool name aliases",
            )
        tool_name: str | None = nested_name
    elif nested_name is not None:
        tool_name = nested_name
    else:
        tool_name = flat_tool

    if not tool_name:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="malformed_event",
            summary="Missing, malformed, or contradictory tool name",
        )

    # 2. Resolve workspace (required)
    workspaces, ws_conflict = _resolve_workspace_paths(payload)
    if ws_conflict or not workspaces:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            disposition="deny",
            reason_code="invalid_workspace",
            summary="Missing, malformed, or contradictory workspace path",
        )
    workspace = workspaces[0]

    # 3. Validate stepIdx (optional int, non-negative, non-bool)
    if "stepIdx" in payload:
        step_idx_raw = payload["stepIdx"]
        if (
            isinstance(step_idx_raw, bool)
            or not isinstance(step_idx_raw, int)
            or step_idx_raw < 0
        ):
            return HostHookResult(
                schema_version=HOST_HOOK_SCHEMA_VERSION,
                event_id=norm_event_id,
                disposition="deny",
                reason_code="malformed_event",
                summary="Malformed stepIdx field",
            )

    # 4. Map tool to canonical action kind (observation only)
    if tool_name in SUPPORTED_FILE_WRITE_TOOLS:
        action = HostHookAction(
            kind="file_write",
            mutation_class="workspace_mutation",
            target_paths=(),
        )
    elif tool_name in SUPPORTED_SHELL_TOOLS:
        action = HostHookAction(
            kind="shell_command",
            mutation_class="unknown",
            target_paths=(),
        )
    else:
        action = HostHookAction(
            kind="other",
            mutation_class="unknown",
            target_paths=(),
        )

    # 5. Construct canonical post_action HostHookEvent
    try:
        return HostHookEvent(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=norm_event_id,
            phase="post_action",
            workspace=workspace,
            action=action,
            source="antigravity",
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


def render_antigravity_post_tool_use_result(
    result: HostHookEvent | HostHookResult,
) -> dict[str, Any]:
    """Project PostToolUse canonical observation into Antigravity output.

    Antigravity PostToolUse output projection is strictly {} — no native
    abort/retry/continue flow control in PostToolUse. Error contents,
    payload data, and summaries are never echoed.
    """
    if not isinstance(result, (HostHookEvent, HostHookResult)):
        raise ValueError(
            "result must be a HostHookEvent or HostHookResult instance"
        )
    return {}
