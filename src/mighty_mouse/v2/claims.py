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
    corpus_digest: str; evaluator_digest: str; protocol_version: str; evidence_bundle_ids: tuple[str, ...]
    issued_at: str; expires_at: str; receipt_digest: str

def issue_claim(*, state_dir: str | Path, wording: str, tier: int, candidate_id: str, model_identity: str, execution_profile: str, evidence: ClaimEvidence, expires_at: datetime, historical: bool = False) -> ClaimReceipt:
    if tier < 0 or tier > 4 or (historical and tier > 1): raise ValueError("claim tier exceeds available evidence")
    if not all((wording, candidate_id, model_identity, execution_profile, evidence.corpus_digest, evidence.evaluator_digest, evidence.protocol_version, evidence.evidence_bundle_ids)): raise ValueError("claim receipt requires complete current evidence identities")
    if expires_at <= datetime.now(timezone.utc): raise ValueError("claim receipt must have a future expiry")
    records = ImmutableStateStore(state_dir).records()
    restricted = any(isinstance(r.value, Restriction) and r.value.candidate_id == candidate_id for r in records)
    fresh = [r.value for r in records if isinstance(r.value, FreshHoldout) and r.value.candidate_id == candidate_id and r.value.experiment_id == evidence.experiment_id]
    valid_fresh = any(h.passed and h.consumed and not h.contaminated and not h.exposed and h.corpus_digest == evidence.corpus_digest and h.protocol_digest == evidence.protocol_version and h.evidence_bundle_id in evidence.evidence_bundle_ids for h in fresh)
    if restricted: raise ValueError("claim evidence is restricted")
    if tier >= 2 and not (valid_fresh and evidence.paired_tasks >= 30 and evidence.preregistered and evidence.protected_categories_pass and evidence.paired_ci_lower is not None and evidence.minimum_effect is not None and evidence.paired_ci_lower > evidence.minimum_effect and evidence.mcnemar_p is not None and evidence.mcnemar_p < .05): raise ValueError("Tier 2 requires qualifying fresh paired holdout evidence")
    if tier >= 3 and not (len(set(evidence.model_identities)) >= 3 and len(set(evidence.model_classes)) >= 2 and len(set(evidence.source_distinct_corpora)) >= 2 and evidence.heterogeneity_reported): raise ValueError("Tier 3 requires replicated model and corpus evidence")
    if tier >= 4 and not all((evidence.adversarial_quarantine_passed, evidence.evaluator_attested, evidence.rollback_exercised, evidence.monitoring_window_dated)): raise ValueError("Tier 4 requires operational verification")
    now = datetime.now(timezone.utc); payload = {"wording":wording,"tier":tier,"candidate_id":candidate_id,"model_identity":model_identity,"execution_profile":execution_profile,"corpus_digest":evidence.corpus_digest,"evaluator_digest":evidence.evaluator_digest,"protocol_version":evidence.protocol_version,"evidence_bundle_ids":evidence.evidence_bundle_ids,"issued_at":now.isoformat(),"expires_at":expires_at.isoformat()}
    return ClaimReceipt(**payload, receipt_digest="sha256:" + sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest())

def receipt_is_current(receipt: ClaimReceipt, *, state_dir: str | Path | None = None, now: datetime | None = None) -> bool:
    if (now or datetime.now(timezone.utc)) >= datetime.fromisoformat(receipt.expires_at): return False
    if state_dir is None: return False
    records = ImmutableStateStore(state_dir).records()
    if any(isinstance(r.value, Restriction) and r.value.candidate_id == receipt.candidate_id for r in records): return False
    experiments = [r.value for r in records if isinstance(r.value, Experiment) and r.value.holdout_nominee_id == receipt.candidate_id and r.value.execution_profile_id == receipt.execution_profile and r.value.protocol_version == receipt.protocol_version]
    evidence = {r.value.evidence_bundle_id: r.value for r in records if isinstance(r.value, EvidenceBundle)}
    if not experiments or any(identifier not in evidence for identifier in receipt.evidence_bundle_ids): return False
    return any(h.passed and h.consumed and not h.contaminated and not h.exposed and h.model_digest == receipt.model_identity and h.execution_profile_id == receipt.execution_profile and h.corpus_digest == receipt.corpus_digest and h.protocol_digest == receipt.protocol_version and h.evidence_bundle_id in receipt.evidence_bundle_ids and h.experiment_id in {e.experiment_id for e in experiments} for r in records if isinstance(r.value, FreshHoldout) for h in (r.value,))
