"""Immutable, expiring claim receipts issued only from durable local evidence."""
from __future__ import annotations
from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
from mighty_mouse.v2.foundation import EvidenceBundle, Experiment, FreshHoldout, ImmutableStateStore, Restriction

@dataclass(frozen=True)
class ClaimEvidence:
    experiment_id: str
    evidence_bundle_ids: tuple[str, ...]
    corpus_digest: str
    evaluator_digest: str
    protocol_version: str
    protocol_digest: str
    paired_tasks: int = 0
    preregistered: bool = False
    paired_ci_lower: float | None = None
    minimum_effect: float | None = None
    mcnemar_p: float | None = None
    protected_categories_pass: bool = False
    model_classes: tuple[str, ...] = ()
    model_identities: tuple[str, ...] = ()
    source_distinct_corpora: tuple[str, ...] = ()
    heterogeneity_reported: bool = False
    adversarial_quarantine_passed: bool = False
    evaluator_attested: bool = False
    rollback_exercised: bool = False
    monitoring_window_dated: bool = False

@dataclass(frozen=True)
class ClaimReceipt:
    wording: str; tier: int; candidate_id: str; model_identity: str; execution_profile: str
    corpus_digest: str; evaluator_digest: str; protocol_version: str; protocol_digest: str; evidence_bundle_ids: tuple[str, ...]
    issued_at: str; expires_at: str; receipt_digest: str

def issue_claim(*, state_dir: str | Path, wording: str, tier: int, candidate_id: str, model_identity: str, execution_profile: str, evidence: ClaimEvidence, expires_at: datetime, historical: bool = False) -> ClaimReceipt:
    if tier < 0 or tier > 4 or (historical and tier > 1): raise ValueError("claim tier exceeds available evidence")
    if not all((wording, candidate_id, model_identity, execution_profile, evidence.corpus_digest, evidence.evaluator_digest, evidence.protocol_version, evidence.protocol_digest, evidence.evidence_bundle_ids)): raise ValueError("claim receipt requires complete current evidence identities")
    if expires_at <= datetime.now(timezone.utc): raise ValueError("claim receipt must have a future expiry")
    records = ImmutableStateStore(state_dir).records()
    restricted = any(isinstance(r.value, Restriction) and r.value.candidate_id == candidate_id for r in records)
    experiment = next((r.value for r in records if isinstance(r.value, Experiment) and r.value.experiment_id == evidence.experiment_id), None)
    bundles: dict[str, list[EvidenceBundle]] = {}
    for record in records:
        if isinstance(record.value, EvidenceBundle):
            bundles.setdefault(record.value.evidence_bundle_id, []).append(record.value)
    expected_digests = dict(zip(experiment.evidence_bundle_ids, experiment.evidence_bundle_digests, strict=True)) if experiment else {}
    bundles_are_current = bool(experiment) and candidate_id in experiment.candidate_ids and experiment.model_digest == model_identity and experiment.execution_profile_id == execution_profile and all(
        identifier in experiment.evidence_bundle_ids
        and len(bundles.get(identifier, ())) == 1
        and bundles[identifier][0].bundle_digest == expected_digests[identifier]
        and bundles[identifier][0].experiment_id == evidence.experiment_id
        and bundles[identifier][0].model_digest == model_identity
        and bundles[identifier][0].execution_profile_id == execution_profile
        and bundles[identifier][0].candidate_id == candidate_id
        for identifier in evidence.evidence_bundle_ids
    )
    fresh = [r.value for r in records if isinstance(r.value, FreshHoldout) and r.value.candidate_id == candidate_id and r.value.experiment_id == evidence.experiment_id]
    valid_fresh = bundles_are_current and any(h.passed and h.consumed and not h.contaminated and not h.exposed and h.corpus_digest == evidence.corpus_digest and h.protocol_digest == evidence.protocol_digest and h.evidence_bundle_id in evidence.evidence_bundle_ids for h in fresh)
    if restricted: raise ValueError("claim evidence is restricted")
    if not bundles_are_current: raise ValueError("claim evidence bundles must exist and match the experiment, candidate, model, and profile")
    if experiment.protocol_version != evidence.protocol_version: raise ValueError("claim protocol version must match the frozen experiment")
    if tier >= 2 and not (valid_fresh and evidence.paired_tasks >= 30 and evidence.preregistered and evidence.protected_categories_pass and evidence.paired_ci_lower is not None and evidence.minimum_effect is not None and evidence.paired_ci_lower > evidence.minimum_effect and evidence.mcnemar_p is not None and evidence.mcnemar_p < .05): raise ValueError("Tier 2 requires qualifying fresh paired holdout evidence")
    if tier >= 3 and not (len(set(evidence.model_identities)) >= 3 and len(set(evidence.model_classes)) >= 2 and len(set(evidence.source_distinct_corpora)) >= 2 and evidence.heterogeneity_reported): raise ValueError("Tier 3 requires replicated model and corpus evidence")
    if tier >= 4 and not all((evidence.adversarial_quarantine_passed, evidence.evaluator_attested, evidence.rollback_exercised, evidence.monitoring_window_dated)): raise ValueError("Tier 4 requires operational verification")
    now = datetime.now(timezone.utc); payload = {"wording":wording,"tier":tier,"candidate_id":candidate_id,"model_identity":model_identity,"execution_profile":execution_profile,"corpus_digest":evidence.corpus_digest,"evaluator_digest":evidence.evaluator_digest,"protocol_version":evidence.protocol_version,"protocol_digest":evidence.protocol_digest,"evidence_bundle_ids":evidence.evidence_bundle_ids,"issued_at":now.isoformat(),"expires_at":expires_at.isoformat()}
    return ClaimReceipt(**payload, receipt_digest="sha256:" + sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest())

def receipt_is_current(receipt: ClaimReceipt, *, state_dir: str | Path | None = None, now: datetime | None = None) -> bool:
    if (now or datetime.now(timezone.utc)) >= datetime.fromisoformat(receipt.expires_at): return False
    if state_dir is None: return False
    records = ImmutableStateStore(state_dir).records()
    if any(isinstance(r.value, Restriction) and r.value.candidate_id == receipt.candidate_id for r in records): return False
    holdouts = [r.value for r in records if isinstance(r.value, FreshHoldout) and r.value.candidate_id == receipt.candidate_id]
    experiments = [r.value for r in records if isinstance(r.value, Experiment) and r.value.experiment_id in {holdout.experiment_id for holdout in holdouts} and r.value.holdout_nominee_id == receipt.candidate_id and receipt.candidate_id in r.value.candidate_ids and r.value.model_digest == receipt.model_identity and r.value.execution_profile_id == receipt.execution_profile and r.value.protocol_version == receipt.protocol_version]
    evidence: dict[str, list[EvidenceBundle]] = {}
    for record in records:
        if isinstance(record.value, EvidenceBundle):
            evidence.setdefault(record.value.evidence_bundle_id, []).append(record.value)
    matching_experiments = [experiment for experiment in experiments if all(
        identifier in experiment.evidence_bundle_ids
        and len(evidence.get(identifier, ())) == 1
        and evidence[identifier][0].bundle_digest == dict(zip(experiment.evidence_bundle_ids, experiment.evidence_bundle_digests, strict=True))[identifier]
        and evidence[identifier][0].experiment_id == experiment.experiment_id
        and evidence[identifier][0].model_digest == receipt.model_identity
        and evidence[identifier][0].execution_profile_id == receipt.execution_profile
        and evidence[identifier][0].candidate_id == receipt.candidate_id
        for identifier in receipt.evidence_bundle_ids
    )]
    if not matching_experiments: return False
    return any(h.passed and h.consumed and not h.contaminated and not h.exposed and h.model_digest == receipt.model_identity and h.execution_profile_id == receipt.execution_profile and h.corpus_digest == receipt.corpus_digest and h.protocol_digest == receipt.protocol_digest and h.evidence_bundle_id in receipt.evidence_bundle_ids and h.experiment_id in {experiment.experiment_id for experiment in matching_experiments} for h in holdouts)
