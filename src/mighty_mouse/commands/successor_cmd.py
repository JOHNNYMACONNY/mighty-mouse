"""Explicit v2 Preview and Pin controls for an Eligible Successor."""

from __future__ import annotations

import json
from uuid import uuid4

from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    ImmutableStateStore,
    Mode,
    Pin,
    PromotionController,
    Preview,
    Scope,
    TaskCategory,
    resolve_model_identity,
)


def _inputs(*, mode: str, repository: str, task_category: str, model_class: str, model_digest: str | None, model_artifact: str | None, execution_profile: str, capabilities: list[str] | None):
    return (
        Scope(Mode(mode), repository, TaskCategory(task_category), model_class),
        resolve_model_identity(artifact_path=model_artifact, artifact_digest=model_digest),
        ExecutionProfile(execution_profile, frozenset(capabilities or [])),
    )


def run_preview(*, state_dir: str, candidate_id: str, evidence_bundle_id: str, mode: str, repository: str, task_category: str, model_class: str, model_digest: str | None, model_artifact: str | None, execution_profile: str, capabilities: list[str] | None, json_output: bool) -> None:
    scope, identity, profile = _inputs(mode=mode, repository=repository, task_category=task_category, model_class=model_class, model_digest=model_digest, model_artifact=model_artifact, execution_profile=execution_profile, capabilities=capabilities)
    selection = ImmutableStateStore(state_dir).preview(
        Preview(f"preview-{uuid4().hex}", scope, candidate_id, evidence_bundle_id, identity.artifact_digest or "", profile.profile_id),
        model_identity=identity,
        execution_profile=profile,
    )
    document = {"interface": "preview", "candidate_id": candidate_id, "policy_id": selection.policy.policy_id, "selection_changed": False}
    print(json.dumps(document, sort_keys=True) if json_output else f"Previewing {candidate_id}; active Champion selection is unchanged.")


def run_pin(*, state_dir: str, candidate_id: str, mode: str, repository: str, task_category: str, model_class: str, model_digest: str | None, model_artifact: str | None, execution_profile: str, capabilities: list[str] | None, json_output: bool) -> None:
    scope, identity, profile = _inputs(mode=mode, repository=repository, task_category=task_category, model_class=model_class, model_digest=model_digest, model_artifact=model_artifact, execution_profile=execution_profile, capabilities=capabilities)
    stored = ImmutableStateStore(state_dir).pin(
        Pin(f"pin-{uuid4().hex}", scope, candidate_id, identity.artifact_digest or "", profile.profile_id),
        model_identity=identity,
        execution_profile=profile,
    )
    document = {"interface": "pin", "candidate_id": candidate_id, "scope": {"mode": mode, "repository": repository, "task_category": task_category, "model_class": model_class}, "record_pointer": stored.record_hash}
    print(json.dumps(document, sort_keys=True) if json_output else f"Pinned active Candidate {candidate_id} for the declared Scope.")


def run_rollback(*, state_dir: str, reason: str, mode: str, repository: str, task_category: str, model_class: str, model_digest: str | None, model_artifact: str | None, execution_profile: str, capabilities: list[str] | None, json_output: bool) -> None:
    scope, identity, profile = _inputs(mode=mode, repository=repository, task_category=task_category, model_class=model_class, model_digest=model_digest, model_artifact=model_artifact, execution_profile=execution_profile, capabilities=capabilities)
    notice = PromotionController(ImmutableStateStore(state_dir)).recover(
        scope=scope, model_identity=identity, execution_profile=profile, reason=reason,
    )
    document = {"interface": "rollback", "action": notice.action, "candidate_id": notice.candidate_id, "reason": notice.reason}
    print(json.dumps(document, sort_keys=True) if json_output else f"Rolled back {notice.candidate_id}: {notice.reason}.")
