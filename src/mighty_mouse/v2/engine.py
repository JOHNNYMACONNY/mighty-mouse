"""PolicyEngine: Deep module facade encapsulating v2 state storage, policy selection, and promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .promotion import PromotionController
from .records import (
    ComputeScalingPin,
    ComputeScalingPolicy,
    EligibleSuccessor,
    ExecutionProfile,
    HybridHandoff,
    ModelIdentity,
    Pin,
    PolicySelection,
    Preview,
    Promotion,
    PromotionNotice,
    Restriction,
    Rollback,
    RoutingDecision,
    Scope,
    Signal,
    StoredRecord,
)
from .store import ImmutableStateStore


def _build_status_document(
    state_dir: str | Path,
    scope: Scope,
    model_identity: ModelIdentity,
    execution_profile: ExecutionProfile,
    policy_engine: PolicyEngine,
) -> dict[str, Any]:
    """Compatibility adapter for the canonical status projection module."""
    from .status import build_status_document

    return build_status_document(
        state_dir,
        scope,
        model_identity,
        execution_profile,
        policy_engine,
    )


def status_document(
    state_dir: str | Path,
    scope: Scope,
    model_identity: ModelIdentity,
    execution_profile: ExecutionProfile,
) -> dict[str, Any]:
    """Compatibility adapter for callers that have not adopted PolicyEngine."""
    return PolicyEngine(state_dir).get_status(scope, model_identity, execution_profile)


class PolicyEngine:
    """A deep module with a minimal public interface encapsulating state persistence, policy resolution, and promotion gates."""

    def __init__(self, state_dir: str | Path) -> None:
        from .signals import SignalLifecycle
        from .telemetry import SignalTelemetry

        self.state_dir = Path(state_dir)
        self._store = ImmutableStateStore(self.state_dir)
        self._promotion_controller = PromotionController(self._store)
        self._signal_lifecycle = SignalLifecycle(self.state_dir)
        self._signal_telemetry = SignalTelemetry(self._signal_lifecycle)

    def select_policy(
        self,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> PolicySelection:
        """Select the effective active Policy for the specified Scope and Execution Profile."""
        if not model_identity.is_complete:
            return self._store._safe_baseline(
                scope.mode, "model identity is incomplete"
            )
        if not execution_profile.is_complete:
            return self._store._safe_baseline(
                scope.mode, "execution profile is incomplete"
            )

        records = self._store.records()
        pin = next(
            (
                record.value
                for record in reversed(records)
                if isinstance(record.value, Pin)
                and record.value.scope == scope
                and record.value.model_digest == model_identity.artifact_digest
                and (
                    record.value.execution_profile_id
                    == execution_profile.profile_id
                )
            ),
            None,
        )
        if pin is not None:
            pinned = self._store._promotion_candidate(
                pin.candidate_id,
                scope,
                model_identity,
                execution_profile,
                records,
            )
            if pinned is not None:
                candidate, record_hash = pinned
                return PolicySelection(
                    candidate.policy,
                    "project_improvement",
                    "exact compatible pinned Champion",
                    record_hash,
                )
            return self._store._safe_baseline(
                scope.mode, "pinned Champion is unavailable"
            )

        rolled_back_promotions = {
            record.value.promotion_id
            for record in records
            if isinstance(record.value, Rollback)
        }
        restricted_candidates = {
            record.value.candidate_id
            for record in records
            if isinstance(record.value, Restriction)
            and record.value.scope == scope
            and record.value.model_digest == model_identity.artifact_digest
            and (
                record.value.execution_profile_id
                == execution_profile.profile_id
            )
        }
        for record in reversed(records):
            if not isinstance(record.value, Promotion):
                continue
            if record.record_hash in rolled_back_promotions:
                continue
            candidate = record.value.eligible_successor.candidate
            if candidate.candidate_id in restricted_candidates:
                continue
            if (
                candidate.scope != scope
                or candidate.model_digest != model_identity.artifact_digest
            ):
                continue
            if not candidate.required_capabilities.issubset(
                execution_profile.capabilities
            ):
                continue
            if (
                execution_profile.profile_id
                not in candidate.compatible_execution_profiles
            ):
                continue
            return PolicySelection(
                candidate.policy,
                "project_improvement",
                "exact compatible Champion",
                record.record_hash,
            )
        return self._store._safe_baseline(
            scope.mode, "no exact compatible Champion"
        )

    def record_signal(self, signal: Signal) -> str | None:
        """Record an immutable, content-free structured observation from routine use."""
        return self._signal_telemetry.collect(signal)

    def pin(
        self,
        value: Pin,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> StoredRecord:
        """Persist a bounded Pin control through the private state adapter."""
        return self._store.pin(value, model_identity=model_identity, execution_profile=execution_profile)

    def preview(
        self,
        value: Preview,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> PolicySelection:
        """Evaluate and persist a bounded Preview without changing selection."""
        return self._store.preview(value, model_identity=model_identity, execution_profile=execution_profile)

    def rollback(
        self,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
        reason: str,
        security_breach: bool = False,
    ) -> PromotionNotice:
        """Recover the active Champion through the private promotion controller."""
        return self._promotion_controller.recover(
            scope=scope,
            model_identity=model_identity,
            execution_profile=execution_profile,
            reason=reason,
            security_breach=security_breach,
        )

    def promote_candidate(
        self,
        successor: EligibleSuccessor,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
        health_check: Callable[[], bool] = lambda: True,
    ) -> tuple[StoredRecord, PromotionNotice]:
        """Execute machine-gated promotion from an Eligible Successor to Champion."""
        return self._promotion_controller.promote(
            successor,
            model_identity=model_identity,
            execution_profile=execution_profile,
            health_check=health_check,
        )

    def append_hybrid_handoff(self, value: HybridHandoff) -> StoredRecord:
        """Persist a routing handoff without exposing the state store."""
        return self._store.append_hybrid_handoff(value)

    def append_routing_decision(self, value: RoutingDecision) -> StoredRecord:
        """Persist a routing decision without exposing the state store."""
        return self._store.append_routing_decision(value)

    def get_status(
        self,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> dict[str, Any]:
        """Generate a complete status document for host UI display or diagnostic inspection."""
        return _build_status_document(
            self.state_dir,
            scope,
            model_identity,
            execution_profile,
            self,
        )

    def resolve_scaling_policy(
        self,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> ComputeScalingPolicy | None:
        """Resolve active exact-compatible compute scaling policy.

        Returns None when unpinned, when model identity or execution
        profile is incomplete, or when no exact matching pin exists.
        """
        if not model_identity.is_complete or not execution_profile.is_complete:
            return None
        scaling_pin = next(
            (
                record.value
                for record in reversed(self._store.records())
                if isinstance(record.value, ComputeScalingPin)
                and record.value.scope == scope
                and record.value.model_digest == model_identity.artifact_digest
                and (
                    record.value.execution_profile_id
                    == execution_profile.profile_id
                )
            ),
            None,
        )
        if scaling_pin is None:
            return None
        return scaling_pin.scaling_policy

    def get_scaling_status(
        self,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> dict[str, Any]:
        """Return active compute scaling policy status for the given scope."""
        scaling_pin = next(
            (
                record.value
                for record in reversed(self._store.records())
                if isinstance(record.value, ComputeScalingPin)
                and record.value.scope == scope
                and record.value.model_digest == model_identity.artifact_digest
                and (
                    record.value.execution_profile_id
                    == execution_profile.profile_id
                )
            ),
            None,
        )
        effective = (
            scaling_pin.scaling_policy
            if scaling_pin
            else ComputeScalingPolicy()
        )
        return {
            "scope": {
                "mode": scope.mode.value,
                "repository": scope.repository,
                "task_category": scope.task_category.value,
                "model_class": scope.model_class,
            },
            "is_pinned": scaling_pin is not None,
            "pin_id": scaling_pin.pin_id if scaling_pin else None,
            "scaling_policy": {
                "variations": effective.variations,
                "temperature_schedule": list(effective.temperature_schedule),
                "consensus_strategy": effective.consensus_strategy,
                "feedback_loop_enabled": effective.feedback_loop_enabled,
            },
        }

    def preview_scaling(
        self,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
        *,
        variations: int = 3,
        temperature_schedule: tuple[float, ...] = (0.0, 0.35, 0.70),
        consensus_strategy: str = "min_diff",
        feedback_loop_enabled: bool = True,
    ) -> dict[str, Any]:
        """Preview compute scaling parameters without persisting them."""
        policy = ComputeScalingPolicy(
            variations=variations,
            temperature_schedule=temperature_schedule,
            consensus_strategy=consensus_strategy,
            feedback_loop_enabled=feedback_loop_enabled,
        )
        return {
            "scope": {
                "mode": scope.mode.value,
                "repository": scope.repository,
                "task_category": scope.task_category.value,
                "model_class": scope.model_class,
            },
            "preview_scaling_policy": {
                "variations": policy.variations,
                "temperature_schedule": list(policy.temperature_schedule),
                "consensus_strategy": policy.consensus_strategy,
                "feedback_loop_enabled": policy.feedback_loop_enabled,
            },
        }

    def pin_scaling(
        self,
        pin: ComputeScalingPin,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> StoredRecord:
        """Persist a bounded ComputeScalingPin record locking scaling
        parameters.
        """
        if not model_identity.is_complete or not execution_profile.is_complete:
            raise ValueError("Incomplete model identity or execution profile")
        if pin.model_digest != model_identity.artifact_digest:
            raise ValueError("Pin model digest does not match model identity")
        if pin.execution_profile_id != execution_profile.profile_id:
            raise ValueError(
                "Pin execution profile ID does not match execution profile"
            )
        return self._store.append(pin)
