"""Versioned domain records and serialization helpers for Mighty Mouse v2."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any, Callable


_SIGNAL_IDENTIFIER = re.compile(r"signal-[0-9]{3,}")
_SIGNAL_REPOSITORY = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
_SIGNAL_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
_SIGNAL_EXECUTION_PROFILE = re.compile(r"sha256:[0-9a-f]{64}")
_SIGNAL_MODEL_CLASSES = frozenset({"local-small", "local-medium", "local-large", "unknown"})
_SIGNAL_FIXED_EXECUTION_PROFILES = frozenset({"codex-local", "unknown"})
_SIGNAL_ENVIRONMENT_VALUES = {
    "os": frozenset({"linux", "macos", "windows", "unknown"}),
    "architecture": frozenset({"x86_64", "arm64", "unknown"}),
    "runtime": frozenset({"codex", "claude-code", "hermes", "cursor", "unknown"}),
}
_REQUIRED_PROMOTION_GATES = ("safety", "security", "provenance", "integrity")
_RECOVERY_REASONS = frozenset({"user_requested", "quality_guard_failed", "verified_security_guard_failure", "verified_provenance_breach", "verified_integrity_breach"})


class Mode(str, Enum):
    CODING = "coding"
    AGENTIC = "agentic"
    HYBRID = "hybrid"


class TaskCategory(str, Enum):
    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"
    FEATURE = "feature"
    DEBUGGING = "debugging"
    REFACTORING = "refactoring"


class ExperimentOutcome(str, Enum):
    COMPLETED = "completed"
    INVALID = "invalid"
    FAILED = "failed"


class EvaluationOutcomeKind(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    INVALID = "invalid"
    TIMEOUT = "timeout"
    ERROR = "error"


class ExperimentDecision(str, Enum):
    NO_CHANGE = "no_change"
    NOMINATE = "nominate"


@dataclass(frozen=True)
class Scope:
    """The explicit boundary within which an improvement record can apply."""

    mode: Mode
    repository: str
    task_category: TaskCategory
    model_class: str

    def __post_init__(self) -> None:
        if not all((self.repository, self.model_class)):
            raise ValueError("Scope requires repository and model_class")


@dataclass(frozen=True)
class Policy:
    policy_id: str
    mode: Mode
    version: str


@dataclass(frozen=True)
class Candidate:
    """An immutable proposed Policy version."""

    candidate_id: str
    policy: Policy
    scope: Scope
    model_digest: str
    required_capabilities: frozenset[str]
    compatible_execution_profiles: frozenset[str]


@dataclass(frozen=True)
class Champion:
    champion_id: str
    candidate_id: str
    scope: Scope
    model_digest: str
    execution_profile_id: str


@dataclass(frozen=True)
class EligibleSuccessor:
    candidate: Candidate
    experiment_id: str
    evidence_bundle_id: str


@dataclass(frozen=True)
class Eligibility:
    """An explainable, non-mutating decision about a nominated Candidate."""

    candidate_id: str
    experiment_id: str | None
    evidence_bundle_id: str | None
    gates: tuple[tuple[str, bool], ...]

    @property
    def is_eligible(self) -> bool:
        return bool(self.experiment_id and self.evidence_bundle_id) and all(passed for _, passed in self.gates)


@dataclass(frozen=True)
class Promotion:
    eligible_successor: EligibleSuccessor
    prior_champion_id: str | None
    machine_gates_passed: bool


@dataclass(frozen=True)
class ComputeScalingPolicy:
    variations: int = 3
    temperature_schedule: tuple[float, ...] = (0.0, 0.35, 0.70)
    consensus_strategy: str = "min_diff"
    feedback_loop_enabled: bool = True


@dataclass(frozen=True)
class ComputeScalingPin:
    pin_id: str
    scope: Scope
    scaling_policy: ComputeScalingPolicy
    model_digest: str
    execution_profile_id: str


@dataclass(frozen=True)
class ModelIdentity:
    artifact_digest: str | None

    @property
    def is_complete(self) -> bool:
        return bool(self.artifact_digest)


@dataclass(frozen=True)
class ExecutionProfile:
    """A canonical record of the execution contract for one run."""

    profile_id: str
    capabilities: frozenset[str]
    runtime_kind: str = "unknown"
    runtime_version: str = "unknown"
    effective_context_limit: int | None = None
    tool_contract_digest: str | None = None
    prompt_template_digest: str | None = None
    sampling_settings: tuple[tuple[str, Any], ...] = ()
    resource_limits: tuple[tuple[str, Any], ...] = ()

    @property
    def is_complete(self) -> bool:
        return bool(self.profile_id) and self.profile_id != "unknown"


@dataclass(frozen=True)
class Signal:
    """A content-free structured observation from routine use."""

    signal_id: str
    scope: Scope
    model_digest: str
    execution_profile_id: str
    outcome: str
    duration_ms: int
    retry_count: int
    verifier_category: str
    verifier_result: str = "not_run"
    environment_metadata: tuple[tuple[str, str], ...] = ()
    rating: int | None = None

    def __post_init__(self) -> None:
        if type(self.duration_ms) is not int or type(self.retry_count) is not int:
            raise ValueError("Signal durations and retry counts must be non-boolean integers")
        if self.duration_ms < 0 or self.retry_count < 0:
            raise ValueError("Signal durations and retry counts must be non-negative")
        if self.outcome not in {"passed", "failed", "cancelled", "error"}:
            raise ValueError("Signal outcome must be controlled and content-free")
        if self.verifier_category not in {"tests", "build", "lint", "typecheck", "manual", "none"}:
            raise ValueError("Signal verifier_category must be controlled and content-free")
        if self.verifier_result not in {"passed", "failed", "not_run"}:
            raise ValueError("Signal verifier_result must be controlled and content-free")
        if self.rating is not None and (type(self.rating) is not int or self.rating not in {1, 2, 3, 4, 5}):
            raise ValueError("Signal rating must be an integer from 1 through 5")
        if not _SIGNAL_IDENTIFIER.fullmatch(self.signal_id):
            raise ValueError("Signal identifier must be controlled and content-free")
        repository_parts = self.scope.repository.split("/")
        if not _SIGNAL_REPOSITORY.fullmatch(self.scope.repository) or any(part in {".", ".."} for part in repository_parts):
            raise ValueError("Signal Scope repository must be a repository identifier, not content or a path")
        if not _SIGNAL_DIGEST.fullmatch(self.model_digest):
            raise ValueError("Signal model_digest must be a sha256 digest")
        if not (_SIGNAL_EXECUTION_PROFILE.fullmatch(self.execution_profile_id) or self.execution_profile_id in _SIGNAL_FIXED_EXECUTION_PROFILES):
            raise ValueError("Signal execution_profile_id must be controlled and content-free")
        if self.scope.model_class not in _SIGNAL_MODEL_CLASSES:
            raise ValueError("Signal provenance must be controlled and content-free")
        if len(self.environment_metadata) > 3:
            raise ValueError("Signal environment metadata is bounded")
        if len({key for key, _ in self.environment_metadata}) != len(self.environment_metadata):
            raise ValueError("Signal environment metadata keys must be unique")
        for key, value in self.environment_metadata:
            if value not in _SIGNAL_ENVIRONMENT_VALUES.get(key, frozenset()):
                raise ValueError("Signal environment metadata must be controlled and content-free")


@dataclass(frozen=True)
class HybridHandoff:
    """Typed Investigation output persisted before Hybrid Coding starts."""

    handoff_id: str
    scope: Scope
    summary: str
    constraints: tuple[str, ...]
    acceptance_checks: tuple[str, ...]
    file_scope: tuple[str, ...]
    risks: tuple[str, ...]

    def __post_init__(self) -> None:
        if self.scope.mode is not Mode.HYBRID:
            raise ValueError("Hybrid handoff requires a Hybrid Scope")
        if not all((self.handoff_id, self.summary, self.acceptance_checks, self.file_scope)):
            raise ValueError("Hybrid handoff requires id, summary, acceptance checks, and file scope")


@dataclass(frozen=True)
class EvidenceBundle:
    """Restricted experiment-specific provenance, referenced only by digest."""

    evidence_bundle_id: str
    experiment_id: str
    model_digest: str
    execution_profile_id: str
    bundle_digest: str
    candidate_id: str | None = None


@dataclass(frozen=True)
class FreshHoldout:
    """Independent fresh-holdout result for one Holdout Contender."""

    candidate_id: str
    scope: Scope
    model_digest: str
    execution_profile_id: str
    passed: bool
    experiment_id: str | None = None
    evidence_bundle_id: str | None = None
    manifest_digest: str | None = None
    corpus_digest: str | None = None
    protocol_digest: str | None = None
    task_digests: tuple[tuple[str, str], ...] = ()
    consumed: bool = True
    contaminated: bool = False
    exposed: bool = False


@dataclass(frozen=True)
class EvaluationOutcome:
    task_id: str
    candidate_id: str
    kind: EvaluationOutcomeKind
    reason: str | None = None
    evidence_bundle_id: str | None = None


@dataclass(frozen=True)
class Experiment:
    """A frozen comparison under one versioned protocol."""

    experiment_id: str
    generation_id: str
    baseline_candidate_id: str
    model_digest: str
    execution_profile_id: str
    candidate_ids: tuple[str, ...]
    evidence_bundle_ids: tuple[str, ...]
    evidence_bundle_digests: tuple[str, ...]
    evaluation_outcomes: tuple[EvaluationOutcome, ...]
    gate_results: tuple[tuple[str, bool], ...]
    protocol_version: str
    outcome: ExperimentOutcome
    decision: ExperimentDecision
    holdout_nominee_id: str | None

    def __post_init__(self) -> None:
        if len(self.evidence_bundle_ids) != len(self.evidence_bundle_digests):
            raise ValueError("Experiment Evidence Bundle identifiers and digests must align")
        if self.decision is ExperimentDecision.NO_CHANGE and self.holdout_nominee_id is not None:
            raise ValueError("Experiment no_change must not name a holdout nominee")
        if self.decision is ExperimentDecision.NOMINATE:
            if self.holdout_nominee_id not in self.candidate_ids:
                raise ValueError("Experiment nominee must be one evaluated Candidate")


@dataclass(frozen=True)
class Generation:
    """An immutable bounded improvement cycle."""

    generation_id: str
    base_champion_id: str | None
    scope: Scope
    model_digest: str
    execution_profile_id: str
    compatible_execution_profile_ids: tuple[str, ...]
    signal_ids: tuple[str, ...]
    signal_aggregate_digest: str
    experiment_ids: tuple[str, ...]
    candidate_ids: tuple[str, ...]
    protocol_version: str
    mutation_budget: int
    seed_schedule: tuple[int, ...]
    task_order: tuple[str, ...]
    condition_order: tuple[str, ...]
    protected_task_categories: tuple[tuple[str, tuple[str, ...]], ...] = ()
    protocol_manifest_digest: str = ""

    def __post_init__(self) -> None:
        if self.mutation_budget < 0:
            raise ValueError("Generation mutation_budget must be non-negative")
        if not all((self.model_digest, self.execution_profile_id, self.signal_aggregate_digest)):
            raise ValueError("Generation requires complete identity, profile, and Signal aggregate")
        if self.execution_profile_id not in self.compatible_execution_profile_ids:
            raise ValueError("Generation compatibility must include its resolved profile")
        validate_protected_task_categories(self.protected_task_categories, self.task_order)


@dataclass(frozen=True)
class Restriction:
    restriction_id: str
    scope: Scope
    candidate_id: str
    model_digest: str
    execution_profile_id: str
    reason: str

    def __post_init__(self) -> None:
        if self.reason not in _RECOVERY_REASONS - {"user_requested", "quality_guard_failed"}:
            raise ValueError("Restriction reason must be a verified controlled security reason")


@dataclass(frozen=True)
class Pin:
    pin_id: str
    scope: Scope
    candidate_id: str
    model_digest: str
    execution_profile_id: str


@dataclass(frozen=True)
class Preview:
    preview_id: str
    scope: Scope
    candidate_id: str
    evidence_bundle_id: str
    model_digest: str
    execution_profile_id: str


@dataclass(frozen=True)
class Rollback:
    rollback_id: str
    scope: Scope
    promotion_id: str
    restored_champion_id: str | None
    model_digest: str
    execution_profile_id: str
    reason: str

    def __post_init__(self) -> None:
        if self.reason not in _RECOVERY_REASONS:
            raise ValueError("Rollback reason must be controlled and content-free")


@dataclass(frozen=True)
class RoutingDecision:
    """Immutable explanation of one selected Mode and its durable routing inputs."""

    scope: Scope
    inferred_mode: Mode
    confidence_percent: int
    selected_mode: Mode
    reason: str
    model_digest: str | None
    execution_profile_id: str


def validate_protected_task_categories(categories: tuple[tuple[str, tuple[str, ...]], ...], task_order: tuple[str, ...]) -> None:
    if not categories:
        raise ValueError("protected task categories must be precommitted")
    if any(not category or not task_ids or not set(task_ids).issubset(task_order) for category, task_ids in categories):
        raise ValueError("protected task categories must name frozen Development Suite tasks")
    if len({category for category, _ in categories}) != len(categories):
        raise ValueError("protected task categories must have unique names")


RecordValue = Champion | Candidate | Promotion | Signal | HybridHandoff | EvidenceBundle | FreshHoldout | EligibleSuccessor | Experiment | Generation | Restriction | Pin | Preview | Rollback | RoutingDecision


@dataclass(frozen=True)
class StoredRecord:
    value: RecordValue
    recorded_at: str
    record_hash: str
    previous_record_hash: str | None
    schema_version: int


@dataclass(frozen=True)
class PolicySelection:
    policy: Policy
    source: str
    reason: str
    record_hash: str | None


@dataclass(frozen=True)
class PromotionNotice:
    """Content-free explanation of a live Champion transition."""

    action: str
    candidate_id: str
    reason: str
    inspect_command: str = "mighty-mouse status --json"
    rollback_command: str = "mighty-mouse rollback"

    def __post_init__(self) -> None:
        if self.action not in {"promoted", "rolled_back", "restricted_and_rolled_back"}:
            raise ValueError("Promotion notice action must be controlled")
        if self.reason not in _RECOVERY_REASONS and self.reason != "eligible_successor_passed_health_checks":
            raise ValueError("Promotion notice reason must be controlled and content-free")


def _record_type(value: RecordValue) -> str:
    return {
        Champion: "champion", Candidate: "candidate", Promotion: "promotion", Signal: "signal", HybridHandoff: "hybrid_handoff", EvidenceBundle: "evidence_bundle", FreshHoldout: "fresh_holdout", EligibleSuccessor: "eligible_successor",
        Experiment: "experiment", Generation: "generation", Restriction: "restriction", Pin: "pin",
        Preview: "preview", Rollback: "rollback", RoutingDecision: "routing_decision", ComputeScalingPin: "compute_scaling_pin",
    }[type(value)]


def _immutable_record_identity(value: RecordValue) -> tuple[str, str] | None:
    if isinstance(value, Candidate):
        return ("candidate", value.candidate_id)
    if isinstance(value, Generation):
        return ("generation", value.generation_id)
    return None


def _to_json_value(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if is_dataclass(value):
        return {key: _to_json_value(item) for key, item in asdict(value).items()}
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, frozenset, set)):
        values = [_to_json_value(item) for item in value]
        return sorted(values) if isinstance(value, (frozenset, set)) else values
    return value


def _scope_from_document(value: dict[str, Any]) -> Scope:
    return Scope(
        Mode(value["mode"]),
        value["repository"],
        TaskCategory(value["task_category"]),
        value["model_class"],
    )


def _candidate(value: dict[str, Any]) -> Candidate:
    policy = value["policy"]
    return Candidate(
        value["candidate_id"],
        Policy(policy["policy_id"], Mode(policy["mode"]), policy["version"]),
        _scope_from_document(value["scope"]),
        value["model_digest"],
        frozenset(value["required_capabilities"]),
        frozenset(value["compatible_execution_profiles"]),
    )


def _record_from_value(record_type: str, value: dict[str, Any]) -> RecordValue:
    if record_type == "champion":
        return Champion(value["champion_id"], value["candidate_id"], _scope_from_document(value["scope"]), value["model_digest"], value["execution_profile_id"])
    if record_type == "candidate": return _candidate(value)
    if record_type == "promotion":
        successor = value["eligible_successor"]
        return Promotion(EligibleSuccessor(_candidate(successor["candidate"]), successor["experiment_id"], successor["evidence_bundle_id"]), value["prior_champion_id"], value["machine_gates_passed"])
    if record_type == "signal":
        return Signal(
            value["signal_id"], _scope_from_document(value["scope"]), value["model_digest"],
            value["execution_profile_id"], value["outcome"], value["duration_ms"],
            value["retry_count"], value["verifier_category"], value.get("verifier_result", "not_run"),
            tuple(tuple(item) for item in value.get("environment_metadata", ())), value.get("rating"),
        )
    if record_type == "hybrid_handoff":
        return HybridHandoff(value["handoff_id"], _scope_from_document(value["scope"]), value["summary"], tuple(value["constraints"]), tuple(value["acceptance_checks"]), tuple(value["file_scope"]), tuple(value["risks"]))
    if record_type == "evidence_bundle":
        return EvidenceBundle(value["evidence_bundle_id"], value["experiment_id"], value["model_digest"], value["execution_profile_id"], value["bundle_digest"], value.get("candidate_id"))
    if record_type == "fresh_holdout":
        return FreshHoldout(value["candidate_id"], _scope_from_document(value["scope"]), value["model_digest"], value["execution_profile_id"], value["passed"], value.get("experiment_id"), value.get("evidence_bundle_id"), value.get("manifest_digest"), value.get("corpus_digest"), value.get("protocol_digest"), tuple(tuple(item) for item in value.get("task_digests", ())), value.get("consumed", False), value.get("contaminated", False), value.get("exposed", False))
    if record_type == "eligible_successor":
        return EligibleSuccessor(_candidate(value["candidate"]), value["experiment_id"], value["evidence_bundle_id"])
    if record_type == "experiment":
        return Experiment(value["experiment_id"], value["generation_id"], value["baseline_candidate_id"], value["model_digest"], value["execution_profile_id"], tuple(value["candidate_ids"]), tuple(value["evidence_bundle_ids"]), tuple(value["evidence_bundle_digests"]), tuple(EvaluationOutcome(item["task_id"], item["candidate_id"], EvaluationOutcomeKind(item["kind"]), item.get("reason"), item.get("evidence_bundle_id")) for item in value["evaluation_outcomes"]), tuple((item[0], item[1]) for item in value["gate_results"]), value["protocol_version"], ExperimentOutcome(value["outcome"]), ExperimentDecision(value["decision"]), value["holdout_nominee_id"])
    if record_type == "generation":
        return Generation(value["generation_id"], value["base_champion_id"], _scope_from_document(value["scope"]), value["model_digest"], value["execution_profile_id"], tuple(value["compatible_execution_profile_ids"]), tuple(value["signal_ids"]), value["signal_aggregate_digest"], tuple(value["experiment_ids"]), tuple(value["candidate_ids"]), value["protocol_version"], value["mutation_budget"], tuple(value["seed_schedule"]), tuple(value["task_order"]), tuple(value["condition_order"]), tuple((item[0], tuple(item[1])) for item in value.get("protected_task_categories", ())), value.get("protocol_manifest_digest", ""))
    if record_type == "restriction":
        return Restriction(value["restriction_id"], _scope_from_document(value["scope"]), value["candidate_id"], value["model_digest"], value["execution_profile_id"], value["reason"])
    if record_type == "pin":
        return Pin(value["pin_id"], _scope_from_document(value["scope"]), value["candidate_id"] if "candidate_id" in value else value["champion_id"], value["model_digest"], value["execution_profile_id"])
    if record_type == "preview":
        return Preview(value["preview_id"], _scope_from_document(value["scope"]), value["candidate_id"], value["evidence_bundle_id"], value["model_digest"], value["execution_profile_id"])
    if record_type == "rollback":
        return Rollback(value["rollback_id"], _scope_from_document(value["scope"]), value["promotion_id"], value["restored_champion_id"], value["model_digest"], value["execution_profile_id"], value["reason"])
    if record_type == "routing_decision":
        return RoutingDecision(_scope_from_document(value["scope"]), Mode(value["inferred_mode"]), value["confidence_percent"], Mode(value["selected_mode"]), value["reason"], value["model_digest"], value["execution_profile_id"])
    if record_type == "compute_scaling_pin":
        sp = value["scaling_policy"]
        scaling_policy = ComputeScalingPolicy(
            variations=int(sp.get("variations", 3)),
            temperature_schedule=tuple(float(t) for t in sp.get("temperature_schedule", (0.0, 0.35, 0.70))),
            consensus_strategy=str(sp.get("consensus_strategy", "min_diff")),
            feedback_loop_enabled=bool(sp.get("feedback_loop_enabled", True)),
        )
        return ComputeScalingPin(
            pin_id=value["pin_id"],
            scope=_scope_from_document(value["scope"]),
            scaling_policy=scaling_policy,
            model_digest=value["model_digest"],
            execution_profile_id=value["execution_profile_id"],
        )
    raise ValueError(f"unknown state record type: {record_type}")


def resolve_execution_profile(*, runtime_kind: str, runtime_version: str, effective_context_limit: int, tool_contract_digest: str, prompt_template_digest: str, sampling_settings: dict[str, Any], resource_limits: dict[str, Any], capabilities: set[str] | frozenset[str]) -> ExecutionProfile:
    """Resolve a stable exact profile digest from normalized execution facts."""
    if not all((runtime_kind, runtime_version, tool_contract_digest, prompt_template_digest)) or effective_context_limit < 1:
        raise ValueError("Execution Profile requires complete runtime and contract facts")
    document = {
        "runtime_kind": runtime_kind, "runtime_version": runtime_version,
        "effective_context_limit": effective_context_limit, "tool_contract_digest": tool_contract_digest,
        "prompt_template_digest": prompt_template_digest, "sampling_settings": sampling_settings,
        "resource_limits": resource_limits, "capabilities": sorted(capabilities),
    }
    profile_id = "sha256:" + sha256(json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return ExecutionProfile(profile_id, frozenset(capabilities), runtime_kind, runtime_version, effective_context_limit, tool_contract_digest, prompt_template_digest, tuple(sorted(sampling_settings.items())), tuple(sorted(resource_limits.items())))


def resolve_model_identity(*, artifact_path: str | Path | None = None, artifact_digest: str | None = None) -> ModelIdentity:
    if artifact_path and artifact_digest:
        raise ValueError("provide either artifact_path or artifact_digest, not both")
    if artifact_path:
        return ModelIdentity("sha256:" + sha256(Path(artifact_path).read_bytes()).hexdigest())
    return ModelIdentity(artifact_digest)
