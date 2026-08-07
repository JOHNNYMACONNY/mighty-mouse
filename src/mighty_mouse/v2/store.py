"""Durable append-only storage for Mighty Mouse v2 state."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone

from hashlib import sha256
import json
import os
from pathlib import Path
from typing import Any

from .records import (
    Candidate,
    Champion,
    Eligibility,
    EligibleSuccessor,
    EvidenceBundle,
    ExecutionProfile,
    Experiment,
    ExperimentDecision,
    ExperimentOutcome,
    FreshHoldout,
    HybridHandoff,
    Mode,
    ModelIdentity,
    Pin,
    Policy,
    PolicySelection,
    Preview,
    Promotion,
    RecordValue,
    Restriction,
    Rollback,
    RoutingDecision,
    Scope,
    Signal,
    StoredRecord,
    _REQUIRED_PROMOTION_GATES,
    _immutable_record_identity,
    _record_from_value,
    _record_type,
    _to_json_value,
)


class ImmutableStateStore:
    """Durable append-only storage for all versioned v2 domain records."""

    filename = "v2-state.jsonl"
    schema_version = 2

    def __init__(self, state_dir: str | Path) -> None:
        self.state_dir = Path(state_dir)
        self.path = self.state_dir / self.filename

    def append(self, value: RecordValue) -> StoredRecord:
        if isinstance(value, Promotion):
            return self.append_promotion(value)
        if isinstance(value, EligibleSuccessor):
            self._validate_eligible_successor(value)
        return self._append(_record_type(value), value)

    def append_candidate(self, value: Candidate) -> StoredRecord:
        return self.append(value)

    def append_champion(self, value: Champion) -> StoredRecord:
        return self.append(value)

    def append_hybrid_handoff(self, value: HybridHandoff) -> StoredRecord:
        return self.append(value)

    def append_routing_decision(self, value: RoutingDecision) -> StoredRecord:
        return self.append(value)

    def append_promotion(self, value: Promotion) -> StoredRecord:
        self._validate_promotion(value)
        candidate = value.eligible_successor.candidate
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_dir / "v2-state.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            self._lock(lock_file)
            try:
                records = self._records_unlocked()
                prior = next((
                    record.value.eligible_successor.candidate.candidate_id
                    for record in reversed(records)
                    if isinstance(record.value, Promotion)
                    and record.value.eligible_successor.candidate.scope == candidate.scope
                    and record.value.eligible_successor.candidate.model_digest == candidate.model_digest
                ), None)
                value = replace(value, prior_champion_id=prior)
                if value.prior_champion_id is not None and not any(
                    isinstance(record.value, EligibleSuccessor)
                    and record.value == value.eligible_successor
                    for record in records
                ):
                    raise ValueError("Promotion requires a recorded Eligible Successor with verified evidence")
                if any(isinstance(record.value, Restriction) and record.value.candidate_id == candidate.candidate_id and record.value.scope == candidate.scope and record.value.model_digest == candidate.model_digest and record.value.execution_profile_id in candidate.compatible_execution_profiles for record in records):
                    raise ValueError("Promotion cannot reactivate a restricted Champion")
                if any(isinstance(record.value, Pin) and record.value.scope == candidate.scope and record.value.model_digest == candidate.model_digest and record.value.execution_profile_id in candidate.compatible_execution_profiles for record in records):
                    raise ValueError("Promotion is blocked by a Pin for this Scope")
                return self._append_locked(_record_type(value), value, records)
            finally:
                self._unlock(lock_file)

    def append_eligible_successor(self, value: EligibleSuccessor, *, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> StoredRecord:
        eligibility = self.eligibility(candidate_id=value.candidate.candidate_id, scope=value.candidate.scope, model_identity=model_identity, execution_profile=execution_profile)
        if not eligibility.is_eligible or (eligibility.experiment_id, eligibility.evidence_bundle_id) != (value.experiment_id, value.evidence_bundle_id):
            raise ValueError("Eligible Successor requires independent fresh-holdout evidence and all gates")
        return self.append(value)

    def _validate_eligible_successor(self, value: EligibleSuccessor) -> None:
        evidence = next(
            (record.value for record in reversed(self.records())
             if isinstance(record.value, EvidenceBundle)
             and record.value.evidence_bundle_id == value.evidence_bundle_id
             and record.value.experiment_id == value.experiment_id),
            None,
        )
        if evidence is None:
            raise ValueError("Eligible Successor requires matching Evidence Bundle")
        eligibility = self.eligibility(
            candidate_id=value.candidate.candidate_id,
            scope=value.candidate.scope,
            model_identity=ModelIdentity(value.candidate.model_digest),
            execution_profile=ExecutionProfile(evidence.execution_profile_id, value.candidate.required_capabilities),
        )
        if not eligibility.is_eligible:
            raise ValueError("Eligible Successor requires independent fresh-holdout evidence and all gates")

    def eligibility(
        self,
        *,
        candidate_id: str,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> Eligibility:
        """Explain the immutable gates required before a Candidate may be used."""
        records = self.records()
        candidate = next(
            (record.value for record in reversed(records)
             if isinstance(record.value, Candidate) and record.value.candidate_id == candidate_id),
            None,
        )
        experiment = next(
            (record.value for record in reversed(records)
             if isinstance(record.value, Experiment)
             and record.value.holdout_nominee_id == candidate_id
             and record.value.outcome is ExperimentOutcome.COMPLETED
             and record.value.decision is ExperimentDecision.NOMINATE),
            None,
        )
        evidence = next(
            (record.value for record in reversed(records)
             if isinstance(record.value, EvidenceBundle)
             and experiment is not None
             and record.value.experiment_id == experiment.experiment_id
             and record.value.evidence_bundle_id in experiment.evidence_bundle_ids),
            None,
        )
        compatibility = bool(
            candidate is not None
            and model_identity.is_complete
            and execution_profile.is_complete
            and candidate.model_digest == model_identity.artifact_digest
            and candidate.required_capabilities.issubset(execution_profile.capabilities)
            and execution_profile.profile_id in candidate.compatible_execution_profiles
        )
        evidence_matches = bool(
            evidence is not None
            and candidate is not None
            and evidence.model_digest == candidate.model_digest
            and evidence.execution_profile_id == execution_profile.profile_id
        )
        experiment_gates = dict(experiment.gate_results) if experiment is not None else {}
        experiment_matches = bool(
            experiment is not None
            and candidate is not None
            and experiment.model_digest == candidate.model_digest
            and experiment.execution_profile_id == execution_profile.profile_id
            and candidate_id in experiment.candidate_ids
        )
        fresh_holdout = next(
            (record.value for record in reversed(records)
             if isinstance(record.value, FreshHoldout)
             and record.value.candidate_id == candidate_id
             and record.value.scope == scope
             and record.value.model_digest == model_identity.artifact_digest
             and record.value.execution_profile_id == execution_profile.profile_id
             and record.value.passed
             and record.value.experiment_id == (experiment.experiment_id if experiment else None)
             and record.value.evidence_bundle_id == (evidence.evidence_bundle_id if evidence else None)
             and all((record.value.manifest_digest, record.value.corpus_digest, record.value.protocol_digest, record.value.task_digests))
             and record.value.consumed and not record.value.contaminated and not record.value.exposed),
            None,
        )
        gates = (
            ("experiment", experiment_matches),
            ("compatibility", compatibility),
            ("evidence", evidence_matches),
            *((gate, experiment_gates.get(gate, False)) for gate in _REQUIRED_PROMOTION_GATES),
            ("freshness", fresh_holdout is not None),
            ("scope", candidate is not None and candidate.scope == scope),
        )
        return Eligibility(
            candidate_id=candidate_id,
            experiment_id=experiment.experiment_id if experiment else None,
            evidence_bundle_id=evidence.evidence_bundle_id if evidence else None,
            gates=gates,
        )

    def preview(self, value: Preview, *, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> PolicySelection:
        """Record a bounded Preview without changing durable policy selection."""
        eligibility = self.eligibility(
            candidate_id=value.candidate_id, scope=value.scope,
            model_identity=model_identity, execution_profile=execution_profile,
        )
        if not eligibility.is_eligible or eligibility.evidence_bundle_id != value.evidence_bundle_id:
            raise ValueError("Preview requires an Eligible Successor with matching evidence")
        if not any(isinstance(record.value, EligibleSuccessor) and record.value.candidate.candidate_id == value.candidate_id for record in self.records()):
            raise ValueError("Preview requires a recorded Eligible Successor")
        if value.model_digest != model_identity.artifact_digest or value.execution_profile_id != execution_profile.profile_id:
            raise ValueError("Preview requires the declared Model Identity and Execution Profile")
        candidate = next(record.value for record in reversed(self.records()) if isinstance(record.value, Candidate) and record.value.candidate_id == value.candidate_id)
        self.append(value)
        return PolicySelection(candidate.policy, "preview", "explicit bounded Preview", None)

    def pin(self, value: Pin, *, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> StoredRecord:
        """Freeze selection to the current compatible Champion for one exact Scope."""
        if value.model_digest != model_identity.artifact_digest or value.execution_profile_id != execution_profile.profile_id:
            raise ValueError("Pin requires the declared Model Identity and Execution Profile")
        selected = self._promotion_candidate(value.candidate_id, value.scope, model_identity, execution_profile)
        if selected is None:
            raise ValueError("Pin requires a current exact compatible Champion")
        return self.append(value)

    @staticmethod
    def _validate_promotion(value: Promotion) -> None:
        if not value.machine_gates_passed:
            raise ValueError("Promotion requires all machine gates to pass")
        if not value.eligible_successor.candidate.model_digest:
            raise ValueError("Promotion requires a complete Model Identity")

    def select_policy(
        self,
        *,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
    ) -> PolicySelection:
        """Compatibility adapter for canonical PolicyEngine selection."""
        from .engine import PolicyEngine

        return PolicyEngine(self.state_dir).select_policy(
            scope=scope,
            model_identity=model_identity,
            execution_profile=execution_profile,
        )

    def _promotion_candidate(
        self,
        candidate_id: str,
        scope: Scope,
        model_identity: ModelIdentity,
        execution_profile: ExecutionProfile,
        records: tuple[StoredRecord, ...] | None = None,
    ) -> tuple[Candidate, str] | None:
        available_records = records if records is not None else self.records()
        rolled_back_promotions = {
            record.value.promotion_id for record in available_records if isinstance(record.value, Rollback)
        }
        restricted_candidates = {
            record.value.candidate_id for record in available_records
            if isinstance(record.value, Restriction)
            and record.value.scope == scope
            and record.value.model_digest == model_identity.artifact_digest
            and record.value.execution_profile_id == execution_profile.profile_id
        }
        for record in reversed(available_records):
            if not isinstance(record.value, Promotion):
                continue
            if record.record_hash in rolled_back_promotions:
                continue
            candidate = record.value.eligible_successor.candidate
            if candidate.candidate_id in restricted_candidates:
                continue
            if candidate.candidate_id != candidate_id or candidate.scope != scope or candidate.model_digest != model_identity.artifact_digest:
                continue
            if not candidate.required_capabilities.issubset(execution_profile.capabilities):
                continue
            if execution_profile.profile_id not in candidate.compatible_execution_profiles:
                continue
            return candidate, record.record_hash
        return None

    def records(self) -> tuple[StoredRecord, ...]:
        if not self.path.exists():
            return ()
        lock_path = self.state_dir / "v2-state.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_SH)
            try:
                return self._records_unlocked()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _records_unlocked(self) -> tuple[StoredRecord, ...]:
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
                existing = self._records_unlocked()
                return self._append_locked(record_type, value, existing)
            finally:
                self._unlock(lock_file)

    def append_many(self, values: tuple[RecordValue, ...]) -> tuple[StoredRecord, ...]:
        """Append a recovery transition while readers are excluded by the state lock."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        lock_path = self.state_dir / "v2-state.lock"
        with lock_path.open("a+", encoding="utf-8") as lock_file:
            self._lock(lock_file)
            try:
                existing = self._records_unlocked()
                stored = []
                for value in values:
                    record = self._append_locked(_record_type(value), value, existing)
                    stored.append(record)
                    existing = (*existing, record)
                return tuple(stored)
            finally:
                self._unlock(lock_file)

    def _append_locked(self, record_type: str, value: RecordValue, existing: tuple[StoredRecord, ...]) -> StoredRecord:
        identity = _immutable_record_identity(value)
        if identity is not None and any(_immutable_record_identity(record.value) == identity for record in existing):
            raise ValueError("duplicate immutable record identity")
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
