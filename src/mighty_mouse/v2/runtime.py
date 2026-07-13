"""Public Autopilot run boundary for v2 Mode routing and Policy selection."""

from __future__ import annotations

from dataclasses import dataclass

from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    HybridHandoff,
    ImmutableStateStore,
    ModelIdentity,
    Mode,
    PolicySelection,
    RoutingDecision,
    Scope,
    TaskCategory,
)


@dataclass(frozen=True)
class AutopilotRunRequest:
    """Inputs needed to choose one scoped Mode and its Effective Policy."""

    repository: str
    task_category: TaskCategory
    model_class: str
    inferred_mode: Mode
    confidence_percent: int
    model_identity: ModelIdentity
    execution_profile: ExecutionProfile
    user_mode: Mode | None = None
    hybrid_handoff: HybridHandoff | None = None

    def __post_init__(self) -> None:
        if not 0 <= self.confidence_percent <= 100:
            raise ValueError("confidence_percent must be between 0 and 100")


@dataclass(frozen=True)
class AutopilotRunResult:
    mode: Mode
    routing_reason: str
    selection: PolicySelection
    handoff_record_hash: str | None = None
    routing_record_hash: str | None = None


def run_autopilot(request: AutopilotRunRequest, store: ImmutableStateStore) -> AutopilotRunResult:
    """Choose a user-facing Mode, then resolve its scoped Effective Policy."""

    handoff_record_hash = None
    if request.user_mode is not None:
        mode = request.user_mode
        routing_reason = "explicit user Mode override"
    elif request.confidence_percent >= 80:
        mode = request.inferred_mode
        routing_reason = "high-confidence inferred Mode"
    elif request.confidence_percent >= 55:
        mode = Mode.HYBRID
        routing_reason = "medium-confidence fixed Hybrid"
    else:
        raise ValueError("explicit user Mode choice is required below 55% confidence")

    scope = Scope(
        mode=mode,
        repository=request.repository,
        task_category=request.task_category,
        model_class=request.model_class,
    )
    if mode is Mode.HYBRID:
        if request.hybrid_handoff is None:
            raise ValueError("a durable Hybrid handoff is required before Coding begins")
        if request.hybrid_handoff.scope != scope:
            raise ValueError("Hybrid handoff Scope must match the selected run Scope")
        handoff_record_hash = store.append_hybrid_handoff(request.hybrid_handoff).record_hash
    selection = store.select_policy(
        scope=scope,
        model_identity=request.model_identity,
        execution_profile=request.execution_profile,
    )
    routing_record = store.append_routing_decision(RoutingDecision(
        scope=scope, inferred_mode=request.inferred_mode, confidence_percent=request.confidence_percent,
        selected_mode=mode, reason=routing_reason, model_digest=request.model_identity.artifact_digest,
        execution_profile_id=request.execution_profile.profile_id,
    ))
    return AutopilotRunResult(
        mode=mode,
        routing_reason=routing_reason,
        selection=selection,
        handoff_record_hash=handoff_record_hash,
        routing_record_hash=routing_record.record_hash,
    )
