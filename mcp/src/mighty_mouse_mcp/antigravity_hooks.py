"""Antigravity PreToolUse host hook executable runner v1.

Accepts Antigravity PreToolUse payload on stdin, adapts it to canonical
HostHookEvent, resolves authoritative AdapterRuntimeContext using the
MCP v6 tool signatures, constructs ResolvedHostHookEvent, and outputs
exactly one JSON object to stdout.

Enforces the core architectural invariant: host payload != authority.
"""

from __future__ import annotations

import json
import secrets
import sys
from typing import Any

from mighty_mouse.host.adapter import (
    MCP_TOOL_CONTRACT_VERSION,
    HostAdapter,
)
from mighty_mouse.host.antigravity import (
    adapt_antigravity_pre_tool_use,
    render_antigravity_pre_tool_use_result,
)
from mighty_mouse.host.hooks import (
    HOST_HOOK_SCHEMA_VERSION,
    HostHookEvent,
    HostHookResult,
    ResolvedHostHookEvent,
)
from mighty_mouse_mcp.server import _get_mcp_tool_signatures


def _generate_event_id() -> str:
    """Generate a privacy-safe unique event ID for internal correlation."""
    return f"ag-pre-{secrets.randbelow(10**30):030d}"


def _make_denial(
    event_id: str,
    reason_code: str,
    summary: str,
) -> HostHookResult:
    """Construct a bounded fail-closed HostHookResult denial."""
    return HostHookResult(
        schema_version=HOST_HOOK_SCHEMA_VERSION,
        event_id=event_id,
        disposition="deny",
        reason_code=reason_code,
        summary=summary,
    )


def run_antigravity_pre_tool_use(
    raw_input: str,
    *,
    event_id: str | None = None,
    tool_signatures: dict[str, Any] | None = None,
    contract_version: int = MCP_TOOL_CONTRACT_VERSION,
) -> dict[str, str]:
    """Execute Antigravity PreToolUse runtime binding from raw JSON string.

    Never raises exceptions: catches any failure and projects a bounded
    canonical HostHookResult denial into Antigravity decision JSON.
    """
    eid = event_id or _generate_event_id()

    # 1. Parse JSON input strictly expecting a JSON object (mapping)
    try:
        payload = json.loads(raw_input)
    except Exception:
        denial = _make_denial(eid, "malformed_event", "Malformed JSON input")
        return render_antigravity_pre_tool_use_result(denial)

    if not isinstance(payload, dict):
        denial = _make_denial(
            eid, "malformed_event", "JSON root must be an object"
        )
        return render_antigravity_pre_tool_use_result(denial)

    # 2. Normalize payload through core Antigravity PreToolUse adapter
    try:
        adapted = adapt_antigravity_pre_tool_use(payload, event_id=eid)
    except Exception:
        denial = _make_denial(eid, "internal_error", "Adapter failure")
        return render_antigravity_pre_tool_use_result(denial)

    if isinstance(adapted, HostHookResult):
        # Already a denial from adapter (e.g. malformed, invalid workspace)
        return render_antigravity_pre_tool_use_result(adapted)

    if not isinstance(adapted, HostHookEvent):
        denial = _make_denial(
            eid, "internal_error", "Unexpected adapter return type"
        )
        return render_antigravity_pre_tool_use_result(denial)

    # 3. Authoritative runtime context resolution
    signatures = (
        tool_signatures
        if tool_signatures is not None
        else _get_mcp_tool_signatures()
    )

    try:
        ctx = HostAdapter.resolve_adapter_context(
            workspace=adapted.workspace,
            tool_signatures=signatures,
            contract_version=contract_version,
        )
    except (ValueError, FileNotFoundError, OSError):
        denial = _make_denial(
            eid,
            "runtime_context_unavailable",
            "Runtime context unavailable",
        )
        return render_antigravity_pre_tool_use_result(denial)
    except Exception:
        denial = _make_denial(
            eid,
            "runtime_context_unavailable",
            "Runtime context resolution failure",
        )
        return render_antigravity_pre_tool_use_result(denial)

    # 4. Construct ResolvedHostHookEvent to confirm valid binding
    try:
        resolved = ResolvedHostHookEvent(
            event=adapted,
            runtime_context=ctx,
        )
        _ = resolved
    except Exception:
        denial = _make_denial(
            eid,
            "runtime_context_unavailable",
            "Resolved event construction failed",
        )
        return render_antigravity_pre_tool_use_result(denial)

    # 5. Non-mutating PreToolUse binding success -> bounded allow
    success_result = HostHookResult(
        schema_version=HOST_HOOK_SCHEMA_VERSION,
        event_id=eid,
        disposition="allow",
        reason_code="not_applicable",
        summary="Action allowed by policy",
    )
    return render_antigravity_pre_tool_use_result(success_result)


def main() -> None:
    """CLI entrypoint reading stdin and printing exactly one JSON object."""
    try:
        raw_input = sys.stdin.read()
    except Exception:
        raw_input = ""

    result = run_antigravity_pre_tool_use(raw_input)
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
