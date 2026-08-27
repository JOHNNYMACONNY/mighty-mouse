"""Antigravity PreToolUse and PostToolUse host hook executable runners v1.

PreToolUse:
Accepts Antigravity PreToolUse payload on stdin, adapts it to canonical
HostHookEvent, resolves authoritative AdapterRuntimeContext using the
MCP v6 tool signatures, constructs ResolvedHostHookEvent, and outputs
exactly one JSON object to stdout.

PostToolUse:
Accepts Antigravity PostToolUse payload on stdin, adapts it to canonical
HostHookEvent (post_action), resolves authoritative AdapterRuntimeContext,
checks process-level opt-in (MIGHTY_MOUSE_POST_ACTION_VERIFY=1), executes
canonical run_verify for file_write actions, converts results to bounded
HookVerificationSummary, records one canonical content-free v2 Signal,
and outputs strictly {} as single JSON object.

Enforces the core architectural invariant: host payload != authority.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import sys
from typing import Any

from mighty_mouse.host.adapter import (
    MCP_TOOL_CONTRACT_VERSION,
    HostAdapter,
)
from mighty_mouse.host.antigravity import (
    adapt_antigravity_post_tool_use,
    adapt_antigravity_pre_tool_use,
    render_antigravity_post_tool_use_result,
    render_antigravity_pre_tool_use_result,
)
from mighty_mouse.host.hooks import (
    HOST_HOOK_SCHEMA_VERSION,
    HookVerificationSummary,
    HostHookEvent,
    HostHookResult,
    ResolvedHostHookEvent,
)
from mighty_mouse.v2.foundation import Mode, Scope, TaskCategory
from mighty_mouse.v2.signals import SignalLifecycle
from mighty_mouse.v2.telemetry import SignalTelemetry
from mighty_mouse_mcp.server import (
    _get_mcp_tool_signatures,
    _verifier_category,
    run_verify,
)

POST_ACTION_VERIFY_ENV = "MIGHTY_MOUSE_POST_ACTION_VERIFY"


def _generate_event_id(prefix: str = "pre") -> str:
    """Generate a privacy-safe unique event ID for internal correlation."""
    return f"ag-{prefix}-{secrets.randbelow(10**30):030d}"


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
    eid = event_id or _generate_event_id("pre")

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


def evaluate_antigravity_post_tool_use(
    raw_input: str,
    *,
    event_id: str | None = None,
    tool_signatures: dict[str, Any] | None = None,
    contract_version: int = MCP_TOOL_CONTRACT_VERSION,
) -> HostHookResult:
    """Evaluate Antigravity PostToolUse returning canonical HostHookResult.

    Resolves authoritative runtime context and executes canonical run_verify
    only when MIGHTY_MOUSE_POST_ACTION_VERIFY is exactly '1' and action is
    an eligible file_write. Persists one canonical content-free v2 Signal
    whenever verification executes.
    """
    eid = event_id or _generate_event_id("post")

    # 1. Parse JSON input strictly expecting a JSON object
    try:
        payload = json.loads(raw_input)
    except Exception:
        return _make_denial(eid, "malformed_event", "Malformed JSON input")

    if not isinstance(payload, dict):
        return _make_denial(
            eid, "malformed_event", "JSON root must be an object"
        )

    # 2. Normalize payload through core PostToolUse adapter
    try:
        adapted = adapt_antigravity_post_tool_use(payload, event_id=eid)
    except Exception:
        return _make_denial(eid, "internal_error", "Adapter failure")

    if isinstance(adapted, HostHookResult):
        return adapted

    if not isinstance(adapted, HostHookEvent):
        return _make_denial(
            eid, "internal_error", "Unexpected adapter return type"
        )

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
        return _make_denial(
            eid,
            "runtime_context_unavailable",
            "Runtime context unavailable",
        )
    except Exception:
        return _make_denial(
            eid,
            "runtime_context_unavailable",
            "Runtime context resolution failure",
        )

    # 4. Construct ResolvedHostHookEvent
    try:
        resolved = ResolvedHostHookEvent(
            event=adapted,
            runtime_context=ctx,
        )
        _ = resolved
    except Exception:
        return _make_denial(
            eid,
            "runtime_context_unavailable",
            "Resolved event construction failed",
        )

    # 5. Check process-level opt-in for verification
    opt_in = os.environ.get(POST_ACTION_VERIFY_ENV) == "1"
    is_eligible_action = adapted.action.kind == "file_write"

    if not opt_in or not is_eligible_action:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=eid,
            disposition="continue",
            reason_code="not_applicable",
            summary="Post-action observation recorded without verification",
            verification=HookVerificationSummary(
                occurred=False,
                passed=None,
                summary="Verification not enabled or not applicable",
            ),
        )

    # 6. Execute canonical run_verify with no host overrides
    try:
        verif_dict = run_verify(adapted.workspace)
    except Exception:
        return HostHookResult(
            schema_version=HOST_HOOK_SCHEMA_VERSION,
            event_id=eid,
            disposition="continue",
            reason_code="internal_error",
            summary="Internal verification execution error",
            verification=HookVerificationSummary(
                occurred=True,
                passed=False,
                summary="Verification execution error",
            ),
        )

    checks = verif_dict.get("checks", [])
    raw_passed = bool(verif_dict.get("passed", False))

    if not checks:
        passed = False
        summary_text = "No executable checks detected"
    else:
        passed = raw_passed
        summary_text = (
            "Verification passed" if passed else "Verification failed"
        )

    reason_code = "verification_passed" if passed else "verification_failed"

    # 7. Record canonical content-free v2 Signal using authoritative context
    try:
        category = _verifier_category(verif_dict)
        scope = Scope(
            mode=Mode.CODING,
            repository=ctx.repository,
            task_category=TaskCategory.UNKNOWN,
            model_class=ctx.model_class,
        )
        lifecycle = SignalLifecycle(Path(ctx.state_dir))
        telemetry = SignalTelemetry(lifecycle)
        duration_ms = round(
            sum(check.get("duration_sec", 0.0) for check in checks) * 1000
        )
        telemetry.record(
            signal_id=f"signal-{secrets.randbelow(10**30):030d}",
            scope=scope,
            model_digest=str(ctx.model_identity.artifact_digest),
            execution_profile_id=str(ctx.execution_profile.profile_id),
            outcome="passed" if passed else "failed",
            duration_ms=duration_ms,
            retry_count=0,
            verifier_category=category,
            verifier_result="passed" if passed else "failed",
        )
    except Exception:
        # Signal recording errors must not alter Host Hook result
        pass

    return HostHookResult(
        schema_version=HOST_HOOK_SCHEMA_VERSION,
        event_id=eid,
        disposition="continue",
        reason_code=reason_code,
        summary=summary_text,
        verification=HookVerificationSummary(
            occurred=True,
            passed=passed,
            summary=summary_text,
        ),
    )


def run_antigravity_post_tool_use(
    raw_input: str,
    *,
    event_id: str | None = None,
    tool_signatures: dict[str, Any] | None = None,
    contract_version: int = MCP_TOOL_CONTRACT_VERSION,
) -> dict[str, Any]:
    """Execute Antigravity PostToolUse returning strictly {} output."""
    res = evaluate_antigravity_post_tool_use(
        raw_input,
        event_id=event_id,
        tool_signatures=tool_signatures,
        contract_version=contract_version,
    )
    return render_antigravity_post_tool_use_result(res)


def main() -> None:
    """PreToolUse CLI entrypoint reading stdin and printing decision JSON."""
    try:
        raw_input = sys.stdin.read()
    except Exception:
        raw_input = ""

    result = run_antigravity_pre_tool_use(raw_input)
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    sys.stdout.flush()


def post_tool_use_main() -> None:
    """PostToolUse CLI entrypoint reading stdin and printing exactly {}."""
    try:
        raw_input = sys.stdin.read()
    except Exception:
        raw_input = ""

    result = run_antigravity_post_tool_use(raw_input)
    sys.stdout.write(json.dumps(result, sort_keys=True) + "\n")
    sys.stdout.flush()


if __name__ == "__main__":
    main()
