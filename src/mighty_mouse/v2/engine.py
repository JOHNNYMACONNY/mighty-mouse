"""PolicyEngine: Deep module facade encapsulating v2 state storage, policy selection, and promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .promotion import PromotionController
from .records import (
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
