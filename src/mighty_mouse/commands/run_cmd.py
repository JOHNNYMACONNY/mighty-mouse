"""CLI adapter for the public v2 Autopilot run boundary."""

from __future__ import annotations

import json
from pathlib import Path

from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    HybridHandoff,
    ImmutableStateStore,
    Mode,
    Scope,
    TaskCategory,
    resolve_model_identity,
)
from mighty_mouse.v2.runtime import AutopilotRunRequest, run_autopilot


def run_run(
    *,
    state_dir: str,
    repository: str,
    task_category: str,
    model_class: str,
    inferred_mode: str,
    confidence_percent: int,
    mode: str | None,
    model_digest: str | None,
    model_artifact: str | None,
    execution_profile: str,
    capabilities: list[str] | None,
    handoff_file: str | None,
    json_output: bool,
) -> None:
    scope = Scope(Mode.HYBRID, repository, TaskCategory(task_category), model_class)
    handoff = _read_handoff(handoff_file, scope) if handoff_file else None
    result = run_autopilot(
        AutopilotRunRequest(
            repository=repository,
            task_category=TaskCategory(task_category),
            model_class=model_class,
            inferred_mode=Mode(inferred_mode),
            confidence_percent=confidence_percent,
            model_identity=resolve_model_identity(
                artifact_path=model_artifact,
                artifact_digest=model_digest,
            ),
            execution_profile=ExecutionProfile(
                profile_id=execution_profile,
                capabilities=frozenset(capabilities or []),
            ),
            user_mode=Mode(mode) if mode else None,
            hybrid_handoff=handoff,
        ),
        ImmutableStateStore(state_dir),
    )
    document = {
        "schema_version": ImmutableStateStore.schema_version,
        "interface": "run",
        "mode": result.mode.value,
        "routing_reason": result.routing_reason,
        "selection": {
            "policy_id": result.selection.policy.policy_id,
            "policy_version": result.selection.policy.version,
            "source": result.selection.source,
            "reason": result.selection.reason,
            "record_hash": result.selection.record_hash,
        },
        "handoff_record_hash": result.handoff_record_hash,
    }
    if json_output:
        print(json.dumps(document, sort_keys=True))
        return

    print(f"Selected Mode: {document['mode']}")
    print(f"Routing: {document['routing_reason']}")
    print(f"Effective Policy: {document['selection']['policy_id']} ({document['selection']['source']})")
    print(f"Reason: {document['selection']['reason']}")


def _read_handoff(path: str, scope: Scope) -> HybridHandoff:
    document = json.loads(Path(path).read_text(encoding="utf-8"))
    return HybridHandoff(
        handoff_id=document["handoff_id"],
        scope=scope,
        summary=document["summary"],
        constraints=tuple(document["constraints"]),
        acceptance_checks=tuple(document["acceptance_checks"]),
        file_scope=tuple(document["file_scope"]),
        risks=tuple(document["risks"]),
    )
