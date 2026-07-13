"""Versioned, immutable foundations for Mighty Mouse v2 state."""

from __future__ import annotations

from dataclasses import asdict, dataclass, is_dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any


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
class Promotion:
    eligible_successor: EligibleSuccessor
    prior_champion_id: str | None
    machine_gates_passed: bool


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

    def __post_init__(self) -> None:
        if self.mutation_budget < 0:
            raise ValueError("Generation mutation_budget must be non-negative")
        if not all((self.model_digest, self.execution_profile_id, self.signal_aggregate_digest)):
            raise ValueError("Generation requires complete identity, profile, and Signal aggregate")
        if self.execution_profile_id not in self.compatible_execution_profile_ids:
            raise ValueError("Generation compatibility must include its resolved profile")


@dataclass(frozen=True)
class Restriction:
    restriction_id: str
    scope: Scope
    candidate_id: str
    model_digest: str
    execution_profile_id: str
    reason: str


@dataclass(frozen=True)
class Pin:
    pin_id: str
    scope: Scope
    champion_id: str
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


@dataclass(frozen=True)
class EvaluationOutcome:
    task_id: str
    candidate_id: str
    kind: EvaluationOutcomeKind


RecordValue = Champion | Candidate | Promotion | Signal | HybridHandoff | EvidenceBundle | Experiment | Generation | Restriction | Pin | Preview | Rollback


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


class ImmutableStateStore:
    """Durable append-only storage for all versioned v2 domain records."""

    filename = "v2-state.jsonl"
    schema_version = 2

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / self.filename

    def append(self, value: RecordValue) -> StoredRecord:
        if isinstance(value, Promotion):
            self._validate_promotion(value)
        return self._append(_record_type(value), value)

    def append_candidate(self, value: Candidate) -> StoredRecord:
        return self.append(value)

    def append_champion(self, value: Champion) -> StoredRecord:
        return self.append(value)

    def append_hybrid_handoff(self, value: HybridHandoff) -> StoredRecord:
        return self.append(value)

    def append_promotion(self, value: Promotion) -> StoredRecord:
        self._validate_promotion(value)
        return self._append(_record_type(value), value)

    @staticmethod
    def _validate_promotion(value: Promotion) -> None:
        if not value.machine_gates_passed:
            raise ValueError("Promotion requires all machine gates to pass")
        if not value.eligible_successor.candidate.model_digest:
            raise ValueError("Promotion requires a complete Model Identity")

    def select_policy(self, *, scope: Scope, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> PolicySelection:
        if not model_identity.is_complete:
            return self._safe_baseline(scope.mode, "model identity is incomplete")
        if not execution_profile.is_complete:
            return self._safe_baseline(scope.mode, "execution profile is incomplete")

        for record in reversed(self.records()):
            if not isinstance(record.value, Promotion):
                continue
            candidate = record.value.eligible_successor.candidate
            if candidate.scope != scope or candidate.model_digest != model_identity.artifact_digest:
                continue
            if not candidate.required_capabilities.issubset(execution_profile.capabilities):
                continue
            if execution_profile.profile_id not in candidate.compatible_execution_profiles:
                continue
            return PolicySelection(candidate.policy, "project_improvement", "exact compatible Champion", record.record_hash)
        return self._safe_baseline(scope.mode, "no exact compatible Champion")

    def records(self) -> tuple[StoredRecord, ...]:
        if not self.path.exists():
            return ()
        records: list[StoredRecord] = []
        previous_record_hash: str | None = None
        for line_number, line in enumerate(self.path.read_text(encoding="utf-8").splitlines(), 1):
            document = json.loads(line)
            if document.get("schema_version") != self.schema_version:
                raise ValueError(f"unsupported state schema at line {line_number}")
            if document.get("previous_record_hash") != previous_record_hash:
                raise ValueError(f"broken state record chain at line {line_number}")
            if document.get("record_hash") != self._hash_document(document):
                raise ValueError(f"invalid state record hash at line {line_number}")
            record = self._record_from_document(document)
            records.append(record)
            previous_record_hash = record.record_hash
        return tuple(records)

    def _append(self, record_type: str, value: RecordValue) -> StoredRecord:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_dir / "v2-state.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            self._lock(lock_file)
            try:
                existing = self.records()
                document = {
                    "schema_version": self.schema_version,
                    "record_type": record_type,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "previous_record_hash": existing[-1].record_hash if existing else None,
                    "value": _to_json_value(value),
                }
                document["record_hash"] = self._hash_document(document)
                with self.path.open("a", encoding="utf-8") as state_file:
                    state_file.write(json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n")
                    state_file.flush()
                    os.fsync(state_file.fileno())
            finally:
                self._unlock(lock_file)
        return self._record_from_document(document)

    @staticmethod
    def _lock(lock_file: Any) -> None:
        import fcntl
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)

    @staticmethod
    def _unlock(lock_file: Any) -> None:
        import fcntl
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    @staticmethod
    def _hash_document(document: dict[str, Any]) -> str:
        payload = {key: value for key, value in document.items() if key != "record_hash"}
        return sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()

    @staticmethod
    def _safe_baseline(mode: Mode, reason: str) -> PolicySelection:
        return PolicySelection(Policy(f"safe-baseline-{mode.value}", mode, "shipped-v2"), "safe_baseline", reason, None)

    @classmethod
    def _record_from_document(cls, document: dict[str, Any]) -> StoredRecord:
        return StoredRecord(
            value=_record_from_value(document["record_type"], document["value"]),
            recorded_at=document["recorded_at"],
            record_hash=document["record_hash"],
            previous_record_hash=document["previous_record_hash"],
            schema_version=document["schema_version"],
        )


def _record_type(value: RecordValue) -> str:
    return {
        Champion: "champion", Candidate: "candidate", Promotion: "promotion", Signal: "signal", HybridHandoff: "hybrid_handoff", EvidenceBundle: "evidence_bundle",
        Experiment: "experiment", Generation: "generation", Restriction: "restriction", Pin: "pin",
        Preview: "preview", Rollback: "rollback",
    }[type(value)]


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
        return EvidenceBundle(value["evidence_bundle_id"], value["experiment_id"], value["model_digest"], value["execution_profile_id"], value["bundle_digest"])
    if record_type == "experiment":
        return Experiment(value["experiment_id"], value["generation_id"], value["baseline_candidate_id"], value["model_digest"], value["execution_profile_id"], tuple(value["candidate_ids"]), tuple(value["evidence_bundle_ids"]), tuple(value["evidence_bundle_digests"]), tuple(EvaluationOutcome(item["task_id"], item["candidate_id"], EvaluationOutcomeKind(item["kind"])) for item in value["evaluation_outcomes"]), tuple((item[0], item[1]) for item in value["gate_results"]), value["protocol_version"], ExperimentOutcome(value["outcome"]), ExperimentDecision(value["decision"]), value["holdout_nominee_id"])
    if record_type == "generation":
        return Generation(value["generation_id"], value["base_champion_id"], _scope_from_document(value["scope"]), value["model_digest"], value["execution_profile_id"], tuple(value["compatible_execution_profile_ids"]), tuple(value["signal_ids"]), value["signal_aggregate_digest"], tuple(value["experiment_ids"]), tuple(value["candidate_ids"]), value["protocol_version"], value["mutation_budget"], tuple(value["seed_schedule"]), tuple(value["task_order"]), tuple(value["condition_order"]))
    if record_type == "restriction":
        return Restriction(value["restriction_id"], _scope_from_document(value["scope"]), value["candidate_id"], value["model_digest"], value["execution_profile_id"], value["reason"])
    if record_type == "pin":
        return Pin(value["pin_id"], _scope_from_document(value["scope"]), value["champion_id"], value["model_digest"], value["execution_profile_id"])
    if record_type == "preview":
        return Preview(value["preview_id"], _scope_from_document(value["scope"]), value["candidate_id"], value["evidence_bundle_id"], value["model_digest"], value["execution_profile_id"])
    if record_type == "rollback":
        return Rollback(value["rollback_id"], _scope_from_document(value["scope"]), value["promotion_id"], value["restored_champion_id"], value["model_digest"], value["execution_profile_id"], value["reason"])
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


def status_document(state_dir: str | Path, scope: Scope, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> dict[str, Any]:
    selection = ImmutableStateStore(state_dir).select_policy(scope=scope, model_identity=model_identity, execution_profile=execution_profile)
    return {
        "schema_version": ImmutableStateStore.schema_version, "interface": "status",
        "scope": _to_json_value(scope), "model_identity": {"artifact_digest": model_identity.artifact_digest},
        "execution_profile": _to_json_value(execution_profile),
        "selection": {"policy_id": selection.policy.policy_id, "policy_version": selection.policy.version, "source": selection.source, "reason": selection.reason, "record_pointer": f"{ImmutableStateStore(state_dir).path}#{selection.record_hash}" if selection.record_hash else None},
    }


def resolve_model_identity(*, artifact_path: str | Path | None = None, artifact_digest: str | None = None) -> ModelIdentity:
    if artifact_path and artifact_digest:
        raise ValueError("provide either artifact_path or artifact_digest, not both")
    if artifact_path:
        return ModelIdentity("sha256:" + sha256(Path(artifact_path).read_bytes()).hexdigest())
    return ModelIdentity(artifact_digest)
