"""PolicyEngine: Deep module facade encapsulating v2 state storage, policy selection, and promotion."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Callable

from .promotion import PromotionController
from .records import (
    Champion,
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
    _record_type,
    _to_json_value,
)
from .store import ImmutableStateStore


def _build_status_document(
    state_dir: str | Path,
    scope: Scope,
    model_identity: ModelIdentity,
    execution_profile: ExecutionProfile,
) -> dict[str, Any]:
    """Generate a complete status document for host UI display or diagnostic inspection."""
    from .signals import SignalLifecycle

    store = ImmutableStateStore(state_dir)
    routing = next((
        record for record in reversed(store.records())
        if isinstance(record.value, RoutingDecision)
        and (record.value.scope.repository, record.value.scope.task_category, record.value.scope.model_class)
        == (scope.repository, scope.task_category, scope.model_class)
    ), None)
    selected_scope = routing.value.scope if routing is not None else scope
    selection = store.select_policy(scope=selected_scope, model_identity=model_identity, execution_profile=execution_profile)
    records = store.records()
    successors = []
    for record in records:
        if not isinstance(record.value, EligibleSuccessor):
            continue
        eligibility = store.eligibility(
            candidate_id=record.value.candidate.candidate_id,
            scope=selected_scope,
            model_identity=model_identity,
            execution_profile=execution_profile,
        )
        successors.append({
            "candidate_id": eligibility.candidate_id,
            "experiment_id": eligibility.experiment_id,
            "evidence_bundle_id": eligibility.evidence_bundle_id,
            "eligible": eligibility.is_eligible,
            "gates": dict(eligibility.gates),
        })
    history = [
        {"kind": "champion" if isinstance(record.value, Promotion) else _record_type(record.value), "record_pointer": record.record_hash}
        for record in records
        if isinstance(record.value, (Champion, Promotion, Pin, Preview, Rollback, Restriction))
    ]
    document = {
        "schema_version": ImmutableStateStore.schema_version, "interface": "status",
        "scope": _to_json_value(selected_scope), "model_identity": {"artifact_digest": model_identity.artifact_digest},
        "execution_profile": _to_json_value(execution_profile),
        "selection": {"policy_id": selection.policy.policy_id, "policy_version": selection.policy.version, "source": selection.source, "reason": selection.reason, "record_pointer": f"{ImmutableStateStore(state_dir).path}#{selection.record_hash}" if selection.record_hash else None},
        "routing": None if routing is None else {"selected_mode": routing.value.selected_mode.value, "reason": routing.value.reason, "record_pointer": f"{store.path}#{routing.record_hash}"},
        "champion": next((
            {"candidate_id": record.value.eligible_successor.candidate.candidate_id, "record_pointer": record.record_hash}
            for record in reversed(records)
            if isinstance(record.value, Promotion) and record.value.eligible_successor.candidate.policy == selection.policy
        ), None),
        "eligible_successors": successors,
        "history": history,
    }
    document["signals"] = SignalLifecycle(state_dir).history(scope=selected_scope)
    return document


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

        self.state_dir = Path(state_dir)
        self._store = ImmutableStateStore(self.state_dir)
        self._promotion_controller = PromotionController(self._store)
        self._signal_lifecycle = SignalLifecycle(self.state_dir)

    def select_policy(
        self,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> PolicySelection:
        """Select the effective active Policy for the specified Scope and Execution Profile."""
        return self._store.select_policy(
            scope=scope,
            model_identity=model_identity,
            execution_profile=execution_profile,
        )

    def record_signal(self, signal: Signal) -> str | None:
        """Record an immutable, content-free structured observation from routine use."""
        return self._signal_lifecycle.collect(signal)

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
        )
