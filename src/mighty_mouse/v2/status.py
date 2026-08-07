"""Canonical status projection for Mighty Mouse v2."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from .records import (
    Champion,
    EligibleSuccessor,
    ExecutionProfile,
    ModelIdentity,
    Pin,
    Preview,
    Promotion,
    Restriction,
    Rollback,
    RoutingDecision,
    Scope,
    _record_type,
    _to_json_value,
)
from .store import ImmutableStateStore

if TYPE_CHECKING:
    from .engine import PolicyEngine


def build_status_document(
    state_dir: str | Path,
    scope: Scope,
    model_identity: ModelIdentity,
    execution_profile: ExecutionProfile,
    policy_engine: PolicyEngine,
) -> dict[str, Any]:
    """Generate the canonical status document for host and CLI consumers."""
    from .signals import SignalLifecycle

    store = ImmutableStateStore(state_dir)
    routing = next((
        record for record in reversed(store.records())
        if isinstance(record.value, RoutingDecision)
        and (
            record.value.scope.repository,
            record.value.scope.task_category,
            record.value.scope.model_class,
        ) == (
            scope.repository,
            scope.task_category,
            scope.model_class,
        )
    ), None)
    selected_scope = routing.value.scope if routing is not None else scope
    selection = policy_engine.select_policy(
        scope=selected_scope,
        model_identity=model_identity,
        execution_profile=execution_profile,
    )
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
        {
            "kind": (
                "champion"
                if isinstance(record.value, Promotion)
                else _record_type(record.value)
            ),
            "record_pointer": record.record_hash,
        }
        for record in records
        if isinstance(
            record.value,
            (Champion, Promotion, Pin, Preview, Rollback, Restriction),
        )
    ]
    document = {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "status",
        "scope": _to_json_value(selected_scope),
        "model_identity": {"artifact_digest": model_identity.artifact_digest},
        "execution_profile": _to_json_value(execution_profile),
        "selection": {
            "policy_id": selection.policy.policy_id,
            "policy_version": selection.policy.version,
            "source": selection.source,
            "reason": selection.reason,
            "record_pointer": (
                f"{ImmutableStateStore(state_dir).path}#"
                f"{selection.record_hash}"
                if selection.record_hash
                else None
            ),
        },
        "routing": (
            None
            if routing is None
            else {
                "selected_mode": routing.value.selected_mode.value,
                "reason": routing.value.reason,
                "record_pointer": f"{store.path}#{routing.record_hash}",
            }
        ),
        "champion": next((
            {
                "candidate_id": (
                    record.value.eligible_successor.candidate.candidate_id
                ),
                "record_pointer": record.record_hash,
            }
            for record in reversed(records)
            if (
                isinstance(record.value, Promotion)
                and (
                    record.value.eligible_successor.candidate.policy
                    == selection.policy
                )
            )
        ), None),
        "eligible_successors": successors,
        "history": history,
    }
    document["signals"] = SignalLifecycle(state_dir).history(
        scope=selected_scope
    )
    return document
