"""Host Hook Recovery Gate v1.

Provides pure, deterministic, non-mutating evaluation of recovery eligibility
for canonical Host Hook events following verification.

Enforces the core architectural invariants:
- host payload != authority
- hard single-attempt budget ceiling (attempts_used == 0)
- strict type and value validation on trusted control inputs
- recovery execution mode is strictly agent-only in v1
- pure evaluation: no agent invocation, no workspace mutation, no telemetry
- internal decision vocabulary: HookRecoveryDecision uses gate_reason
  (not canonical HostHookResult.reason_code) to keep internal decision
  semantics distinct from the core host hook contract.
"""

from __future__ import annotations

from dataclasses import dataclass

from mighty_mouse.host.hooks import (
    HookRecoveryExecutionMode,
    HookVerificationSummary,
    ResolvedHostHookEvent,
)

MAX_RECOVERY_ATTEMPTS: int = 1


@dataclass(frozen=True)
class HookRecoveryDecision:
    """Immutable internal result envelope representing recovery eligibility.

    Uses `gate_reason` to distinguish internal evaluation reasons from
    the canonical HostHookResult `reason_code` closed vocabulary.
    Enforces that eligible v1 decisions are strictly agent execution mode.
    """

    eligible: bool
    gate_reason: str
    summary: str
    execution_mode: HookRecoveryExecutionMode | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.eligible, bool):
            raise ValueError("eligible must be a boolean")
        if not isinstance(self.gate_reason, str) or not self.gate_reason:
            raise ValueError("gate_reason must be a non-empty string")
        if not isinstance(self.summary, str):
            raise ValueError("summary must be a string")
        if self.eligible and self.execution_mode != "agent":
            raise ValueError(
                "execution_mode must be 'agent' when eligible is True"
            )
        if not self.eligible and self.execution_mode is not None:
            raise ValueError(
                "execution_mode must be None when eligible is False"
            )


def evaluate_recovery_gate(
    resolved_event: ResolvedHostHookEvent,
    verification: HookVerificationSummary | None,
    *,
    enabled: bool = False,
    attempts_used: int = 0,
    recovery_in_progress: bool = False,
) -> HookRecoveryDecision:
    """Evaluate recovery eligibility for a canonical resolved host hook event.

    Pure, deterministic function without side-effects.

    Required semantics:
    1. Strict validation of control arguments (reject non-bools, negative).
    2. Verification absent, not occurred, passed is True, or indeterminate
       (passed is None) -> not_applicable. Recovery requires explicit
       verification.occurred is True and verification.passed is False.
    3. Action kind not file_write or mutation class not workspace_mutation
       -> not_applicable.
    4. Recovery disabled -> recovery_not_enabled.
    5. Recovery already active (recursive hook) -> recursive_hook_suppressed.
    6. attempts_used >= MAX_RECOVERY_ATTEMPTS (1) -> retry_budget_exhausted.
    7. All gates satisfied -> eligible = True,
       gate_reason = "eligible", execution_mode = "agent".
    """
    # 1. Strict validation of input arguments (no silent coercion)
    if not isinstance(resolved_event, ResolvedHostHookEvent):
        raise ValueError(
            "resolved_event must be a ResolvedHostHookEvent instance"
        )

    if verification is not None and not isinstance(
        verification, HookVerificationSummary
    ):
        raise ValueError(
            "verification must be a HookVerificationSummary instance or None"
        )

    if isinstance(enabled, bool):
        is_enabled = enabled
    else:
        raise ValueError("enabled must be a boolean")

    if isinstance(attempts_used, bool) or not isinstance(attempts_used, int):
        raise ValueError(
            "attempts_used must be an integer, not bool or other type"
        )
    if attempts_used < 0:
        raise ValueError("attempts_used must be non-negative")

    if isinstance(recovery_in_progress, bool):
        in_progress = recovery_in_progress
    else:
        raise ValueError("recovery_in_progress must be a boolean")

    # 2. Check verification condition: requires explicit failed verification
    if (
        verification is None
        or not verification.occurred
        or verification.passed is not False
    ):
        return HookRecoveryDecision(
            eligible=False,
            gate_reason="not_applicable",
            summary="Verification did not fail; recovery is not applicable",
            execution_mode=None,
        )

    # 3. Check action kind / mutation class: file_write + workspace_mutation
    event = resolved_event.event
    if (
        event.action.kind != "file_write"
        or event.action.mutation_class != "workspace_mutation"
    ):
        return HookRecoveryDecision(
            eligible=False,
            gate_reason="not_applicable",
            summary=(
                "Action kind or mutation class is not eligible for recovery"
            ),
            execution_mode=None,
        )

    # 4. Check explicit enablement
    if not is_enabled:
        return HookRecoveryDecision(
            eligible=False,
            gate_reason="recovery_not_enabled",
            summary=(
                "Self-healing recovery is not enabled in runtime configuration"
            ),
            execution_mode=None,
        )

    # 5. Check recursion guard
    if in_progress:
        return HookRecoveryDecision(
            eligible=False,
            gate_reason="recursive_hook_suppressed",
            summary=(
                "Recovery is already in progress; suppressing recursive "
                "recovery"
            ),
            execution_mode=None,
        )

    # 6. Check retry budget ceiling
    if attempts_used >= MAX_RECOVERY_ATTEMPTS:
        return HookRecoveryDecision(
            eligible=False,
            gate_reason="retry_budget_exhausted",
            summary="Recovery retry budget has been exhausted",
            execution_mode=None,
        )

    # 7. Eligible for v1 agent-only recovery
    return HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="Recovery eligible for execution via agent",
        execution_mode="agent",
    )
