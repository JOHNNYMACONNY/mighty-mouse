"""Policy lifecycle state machine and policy resolution seam for Mighty Mouse v2."""

from __future__ import annotations

from enum import Enum
from typing import Optional, Dict, Any

from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    ImmutableStateStore,
    ModelIdentity,
    Policy,
    PolicySelection,
    Scope,
)


class PolicyState(str, Enum):
    PINNED = "PINNED"
    CHAMPION = "CHAMPION"
    DEGRADED = "DEGRADED"
    ROLLBACK = "ROLLBACK"


class PolicyLifecycle:
    """Manages Policy state transitions, pin overrides, and quality-degradation rollbacks."""

    def __init__(
        self,
        store: ImmutableStateStore,
        pinned_policies: Optional[Dict[str, Policy]] = None,
        min_pass_rate_threshold: float = 0.50,
    ):
        self.store = store
        self.pinned_policies = pinned_policies or {}
        self.min_pass_rate_threshold = min_pass_rate_threshold

    def determine_state(
        self,
        scope: Scope,
        recent_pass_rate: Optional[float] = None,
    ) -> PolicyState:
        scope_key = f"{scope.mode.value}:{scope.task_category.value}:{scope.model_class}"
        if scope_key in self.pinned_policies or scope.mode.value in self.pinned_policies:
            return PolicyState.PINNED

        if recent_pass_rate is not None and recent_pass_rate < self.min_pass_rate_threshold:
            return PolicyState.ROLLBACK

        return PolicyState.CHAMPION

    def resolve_policy(
        self,
        scope: Scope,
        model_identity: Optional[ModelIdentity] = None,
        execution_profile: Optional[ExecutionProfile] = None,
        recent_pass_rate: Optional[float] = None,
    ) -> PolicySelection:
        state = self.determine_state(scope, recent_pass_rate)

        if state == PolicyState.PINNED:
            scope_key = f"{scope.mode.value}:{scope.task_category.value}:{scope.model_class}"
            pinned_policy = self.pinned_policies.get(scope_key) or self.pinned_policies.get(scope.mode.value)
            if pinned_policy:
                return PolicySelection(
                    policy=pinned_policy,
                    source="explicit_pinned_policy",
                    reason=f"Explicit pin configured for scope {scope_key}",
                    record_hash=None,
                )

        if state == PolicyState.ROLLBACK:
            safe_baseline_policy = Policy(
                policy_id=f"safe-baseline-{scope.mode.value}",
                mode=scope.mode,
                version="shipped-v2",
            )
            return PolicySelection(
                policy=safe_baseline_policy,
                source="quality_degradation_rollback",
                reason=f"Recent pass rate ({recent_pass_rate}) below threshold ({self.min_pass_rate_threshold})",
                record_hash=None,
            )

        if model_identity is None:
            model_identity = ModelIdentity(artifact_digest=None)
        if execution_profile is None:
            execution_profile = ExecutionProfile(profile_id="default", capabilities=frozenset())

        # Champion state fallback to store's selection logic
        return self.store.select_policy(
            scope=scope,
            model_identity=model_identity,
            execution_profile=execution_profile,
        )


def resolve_effective_policy(
    scope: Scope,
    store: ImmutableStateStore,
    model_identity: Optional[ModelIdentity] = None,
    execution_profile: Optional[ExecutionProfile] = None,
    recent_pass_rate: Optional[float] = None,
    pinned_policies: Optional[Dict[str, Policy]] = None,
) -> PolicySelection:
    """High-level seam for resolving effective policy for a given run Scope."""
    lifecycle = PolicyLifecycle(store=store, pinned_policies=pinned_policies)
    return lifecycle.resolve_policy(
        scope=scope,
        model_identity=model_identity,
        execution_profile=execution_profile,
        recent_pass_rate=recent_pass_rate,
    )
