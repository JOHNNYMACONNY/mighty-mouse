"""Guarded live promotion controller for Mighty Mouse v2."""

from __future__ import annotations

from typing import Callable

from .records import (
    EligibleSuccessor,
    ExecutionProfile,
    ModelIdentity,
    Promotion,
    PromotionNotice,
    RecordValue,
    Restriction,
    Rollback,
    Scope,
    StoredRecord,
)
from .store import ImmutableStateStore


class PromotionController:
    """Owns the guarded live transition from an Eligible Successor to Champion."""

    def __init__(self, store: ImmutableStateStore) -> None:
        self.store = store

    def promote(self, successor: EligibleSuccessor, *, model_identity: ModelIdentity, execution_profile: ExecutionProfile, health_check: Callable[[], bool]) -> tuple[StoredRecord, PromotionNotice]:
        candidate = successor.candidate
        if not health_check():
            raise ValueError("Promotion controller health check must pass before activation")
        eligibility = self.store.eligibility(candidate_id=candidate.candidate_id, scope=candidate.scope, model_identity=model_identity, execution_profile=execution_profile)
        if not eligibility.is_eligible or (eligibility.experiment_id, eligibility.evidence_bundle_id) != (successor.experiment_id, successor.evidence_bundle_id):
            raise ValueError("Promotion requires a current exact Eligible Successor")
        prior = self._active_promotion(candidate.scope, model_identity, execution_profile)
        stored = self.store.append_promotion(Promotion(successor, prior.value.eligible_successor.candidate.candidate_id if prior else None, True))
        return stored, PromotionNotice("promoted", candidate.candidate_id, "eligible_successor_passed_health_checks")

    def recover(self, *, scope: Scope, model_identity: ModelIdentity, execution_profile: ExecutionProfile, reason: str, security_breach: bool = False) -> PromotionNotice:
        active = self._active_promotion(scope, model_identity, execution_profile)
        if active is None:
            raise ValueError("Recovery requires a current exact compatible Champion")
        candidate = active.value.eligible_successor.candidate
        values: tuple[RecordValue, ...] = ()
        security_breach = security_breach or reason.startswith("verified_")
        if security_breach:
            values += (Restriction(f"restriction-{active.record_hash[:12]}", scope, candidate.candidate_id, candidate.model_digest, execution_profile.profile_id, reason),)
        values += (Rollback(f"rollback-{active.record_hash[:12]}", scope, active.record_hash, active.value.prior_champion_id, candidate.model_digest, execution_profile.profile_id, reason),)
        self.store.append_many(values)
        return PromotionNotice("restricted_and_rolled_back" if security_breach else "rolled_back", candidate.candidate_id, reason)

    def enforce_live_guards(self, *, scope: Scope, model_identity: ModelIdentity, execution_profile: ExecutionProfile, quality_guard: Callable[[], bool], security_guard: Callable[[], bool]) -> PromotionNotice | None:
        """Automatically recover the live Champion when an independent guard fails."""
        if not security_guard():
            return self.recover(scope=scope, model_identity=model_identity, execution_profile=execution_profile, reason="verified_security_guard_failure", security_breach=True)
        if not quality_guard():
            return self.recover(scope=scope, model_identity=model_identity, execution_profile=execution_profile, reason="quality_guard_failed")
        return None

    def _active_promotion(self, scope: Scope, model_identity: ModelIdentity, execution_profile: ExecutionProfile) -> StoredRecord | None:
        records = self.store.records()
        rolled_back = {record.value.promotion_id for record in records if isinstance(record.value, Rollback)}
        restricted = {
            record.value.candidate_id for record in records
            if isinstance(record.value, Restriction)
            and record.value.scope == scope
            and record.value.model_digest == model_identity.artifact_digest
            and record.value.execution_profile_id == execution_profile.profile_id
        }
        for record in reversed(records):
            if not isinstance(record.value, Promotion) or record.record_hash in rolled_back:
                continue
            candidate = record.value.eligible_successor.candidate
            if candidate.candidate_id in restricted or candidate.scope != scope or candidate.model_digest != model_identity.artifact_digest:
                continue
            if execution_profile.profile_id in candidate.compatible_execution_profiles and candidate.required_capabilities.issubset(execution_profile.capabilities):
                return record
        return None
