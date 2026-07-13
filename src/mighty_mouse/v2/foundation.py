"""Immutable v2 state records and scope-aware Policy selection."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any


class Mode(str, Enum):
    """The user-facing execution choice."""

    CODING = "coding"
    AGENTIC = "agentic"
    HYBRID = "hybrid"


class TaskCategory(str, Enum):
    """The controlled vocabulary used to segment v2 execution state."""

    UNKNOWN = "unknown"
    MAINTENANCE = "maintenance"
    FEATURE = "feature"
    DEBUGGING = "debugging"
    REFACTORING = "refactoring"


@dataclass(frozen=True)
class Scope:
    """The explicit boundary within which a Policy can apply."""

    mode: Mode
    repository: str
    task_category: TaskCategory
    model_class: str

    def __post_init__(self) -> None:
        if not all((self.repository, self.model_class)):
            raise ValueError("Scope requires repository and model_class")


@dataclass(frozen=True)
class Policy:
    """A versioned internal rule set for one Mode."""

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
    """The active Candidate for its explicit Scope."""

    candidate: Candidate


@dataclass(frozen=True)
class EligibleSuccessor:
    """A verified Candidate allowed to enter the Promotion gate."""

    candidate: Candidate
    experiment_id: str
    evidence_bundle_id: str


@dataclass(frozen=True)
class Promotion:
    """The auditable, machine-gated activation of an Eligible Successor."""

    eligible_successor: EligibleSuccessor
    prior_champion_id: str | None
    machine_gates_passed: bool


@dataclass(frozen=True)
class ModelIdentity:
    """The exact artifact identity used for compatibility checks."""

    artifact_digest: str | None

    @property
    def is_complete(self) -> bool:
        return bool(self.artifact_digest)


@dataclass(frozen=True)
class ExecutionProfile:
    """The host/runtime profile and observed capabilities for a run."""

    profile_id: str
    capabilities: frozenset[str]


@dataclass(frozen=True)
class StoredRecord:
    """A tamper-evident immutable record stored in the local append-only ledger."""

    value: Candidate | Promotion
    recorded_at: str
    record_hash: str
    previous_record_hash: str | None


@dataclass(frozen=True)
class PolicySelection:
    """The Policy selected for a run, including an explainable reason."""

    policy: Policy
    source: str
    reason: str
    record_hash: str | None


class ImmutableStateStore:
    """A small local append-only ledger for v2 Candidates and Champions."""

    filename = "v2-state.jsonl"
    schema_version = 1

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / self.filename

    def append_candidate(self, candidate: Candidate) -> StoredRecord:
        return self._append("candidate", candidate)

    def append_promotion(self, promotion: Promotion) -> StoredRecord:
        if not promotion.machine_gates_passed:
            raise ValueError("Promotion requires all machine gates to pass")
        if not promotion.eligible_successor.candidate.model_digest:
            raise ValueError("Promotion requires a complete Model Identity")
        return self._append("promotion", promotion)

    def select_policy(
        self,
        *,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> PolicySelection:
        if not model_identity.is_complete:
            return self._safe_baseline(scope.mode, "model identity is incomplete")

        promotions = [
            record for record in self.records() if isinstance(record.value, Promotion)
        ]
        for record in reversed(promotions):
            promotion = record.value
            candidate = promotion.eligible_successor.candidate
            if candidate.scope != scope:
                continue
            if candidate.model_digest != model_identity.artifact_digest:
                continue
            if not candidate.required_capabilities.issubset(execution_profile.capabilities):
                continue
            if execution_profile.profile_id not in candidate.compatible_execution_profiles:
                continue
            return PolicySelection(
                policy=candidate.policy,
                source="project_improvement",
                reason="exact compatible Champion",
                record_hash=record.record_hash,
            )

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
            expected_hash = self._hash_document(document)
            if document.get("record_hash") != expected_hash:
                raise ValueError(f"invalid state record hash at line {line_number}")
            record = self._record_from_document(document)
            records.append(record)
            previous_record_hash = record.record_hash
        return tuple(records)

    def _append(self, record_type: str, value: Candidate | Promotion) -> StoredRecord:
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_dir / "v2-state.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            self._lock(lock_file)
            try:
                existing_records = self.records()
                previous_record_hash = existing_records[-1].record_hash if existing_records else None
                document = {
                    "schema_version": self.schema_version,
                    "record_type": record_type,
                    "recorded_at": datetime.now(timezone.utc).isoformat(),
                    "previous_record_hash": previous_record_hash,
                    "value": self._value_to_document(value),
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
    def _safe_baseline(mode: Mode, reason: str) -> PolicySelection:
        return PolicySelection(
            policy=Policy(
                policy_id=f"safe-baseline-{mode.value}",
                mode=mode,
                version="shipped-v2",
            ),
            source="safe_baseline",
            reason=reason,
            record_hash=None,
        )

    @staticmethod
    def _hash_document(document: dict[str, Any]) -> str:
        payload = {key: value for key, value in document.items() if key != "record_hash"}
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return sha256(encoded).hexdigest()

    @staticmethod
    def _value_to_document(value: Candidate | Promotion) -> dict[str, Any]:
        candidate = (
            value.eligible_successor.candidate if isinstance(value, Promotion) else value
        )
        document = {
            "candidate_id": candidate.candidate_id,
            "policy": asdict(candidate.policy),
            "scope": asdict(candidate.scope),
            "model_digest": candidate.model_digest,
            "required_capabilities": sorted(candidate.required_capabilities),
            "compatible_execution_profiles": sorted(candidate.compatible_execution_profiles),
        }
        if isinstance(value, Promotion):
            document["promotion"] = {
                "experiment_id": value.eligible_successor.experiment_id,
                "evidence_bundle_id": value.eligible_successor.evidence_bundle_id,
                "prior_champion_id": value.prior_champion_id,
                "machine_gates_passed": value.machine_gates_passed,
            }
        return document

    @classmethod
    def _record_from_document(cls, document: dict[str, Any]) -> StoredRecord:
        value = document["value"]
        candidate = Candidate(
            candidate_id=value["candidate_id"],
            policy=Policy(
                policy_id=value["policy"]["policy_id"],
                mode=Mode(value["policy"]["mode"]),
                version=value["policy"]["version"],
            ),
            scope=Scope(
                mode=Mode(value["scope"]["mode"]),
                repository=value["scope"]["repository"],
                task_category=TaskCategory(value["scope"]["task_category"]),
                model_class=value["scope"]["model_class"],
            ),
            model_digest=value["model_digest"],
            required_capabilities=frozenset(value["required_capabilities"]),
            compatible_execution_profiles=frozenset(value["compatible_execution_profiles"]),
        )
        if document["record_type"] == "candidate":
            stored_value: Candidate | Promotion = candidate
        elif document["record_type"] == "promotion":
            promotion = value["promotion"]
            stored_value = Promotion(
                eligible_successor=EligibleSuccessor(
                    candidate=candidate,
                    experiment_id=promotion["experiment_id"],
                    evidence_bundle_id=promotion["evidence_bundle_id"],
                ),
                prior_champion_id=promotion["prior_champion_id"],
                machine_gates_passed=promotion["machine_gates_passed"],
            )
        else:
            raise ValueError(f"unknown state record type: {document['record_type']}")
        return StoredRecord(
            value=stored_value,
            recorded_at=document["recorded_at"],
            record_hash=document["record_hash"],
            previous_record_hash=document["previous_record_hash"],
        )


def status_document(
    state_dir: str | Path,
    scope: Scope,
    model_identity: ModelIdentity,
    execution_profile: ExecutionProfile,
) -> dict[str, Any]:
    """Return the read-only state view rendered by the CLI and host integrations."""

    selection = ImmutableStateStore(state_dir).select_policy(
        scope=scope,
        model_identity=model_identity,
        execution_profile=execution_profile,
    )
    return {
        "schema_version": 1,
        "interface": "status",
        "scope": {
            "mode": scope.mode.value,
            "repository": scope.repository,
            "task_category": scope.task_category.value,
            "model_class": scope.model_class,
        },
        "model_identity": {"artifact_digest": model_identity.artifact_digest},
        "execution_profile": {
            "profile_id": execution_profile.profile_id,
            "capabilities": sorted(execution_profile.capabilities),
        },
        "selection": {
            "policy_id": selection.policy.policy_id,
            "policy_version": selection.policy.version,
            "source": selection.source,
            "reason": selection.reason,
            "record_pointer": (
                f"{ImmutableStateStore(state_dir).path}#{selection.record_hash}"
                if selection.record_hash
                else None
            ),
        },
    }


def resolve_model_identity(
    *, artifact_path: str | Path | None = None, artifact_digest: str | None = None
) -> ModelIdentity:
    """Resolve identity from an artifact fingerprint, rejecting ambiguous input."""

    if artifact_path and artifact_digest:
        raise ValueError("provide either artifact_path or artifact_digest, not both")
    if artifact_path:
        digest = sha256(Path(artifact_path).read_bytes()).hexdigest()
        return ModelIdentity(f"sha256:{digest}")
    return ModelIdentity(artifact_digest)
