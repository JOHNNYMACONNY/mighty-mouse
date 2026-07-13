"""Immutable, expiring, evidence-bound public claim receipts."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json


@dataclass(frozen=True)
class ClaimReceipt:
    wording: str
    tier: int
    candidate_id: str
    model_identity: str
    execution_profile: str
    corpus_digest: str
    evaluator_digest: str
    protocol_version: str
    evidence_bundle_ids: tuple[str, ...]
    issued_at: str
    expires_at: str
    receipt_digest: str


def issue_claim(*, wording: str, tier: int, candidate_id: str, model_identity: str, execution_profile: str, corpus_digest: str, evaluator_digest: str, protocol_version: str, evidence_bundle_ids: tuple[str, ...], expires_at: datetime, historical: bool = False) -> ClaimReceipt:
    if not all((wording, candidate_id, model_identity, execution_profile, corpus_digest, evaluator_digest, protocol_version, evidence_bundle_ids)):
        raise ValueError("claim receipt requires complete current evidence identities")
    if tier < 0 or tier > 4 or (historical and tier > 1):
        raise ValueError("claim tier exceeds available evidence")
    now = datetime.now(timezone.utc)
    if expires_at <= now:
        raise ValueError("claim receipt must have a future expiry")
    payload = {"wording": wording, "tier": tier, "candidate_id": candidate_id, "model_identity": model_identity, "execution_profile": execution_profile, "corpus_digest": corpus_digest, "evaluator_digest": evaluator_digest, "protocol_version": protocol_version, "evidence_bundle_ids": evidence_bundle_ids, "issued_at": now.isoformat(), "expires_at": expires_at.isoformat()}
    digest = "sha256:" + sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return ClaimReceipt(**payload, receipt_digest=digest)


def receipt_is_current(receipt: ClaimReceipt, *, now: datetime | None = None) -> bool:
    return (now or datetime.now(timezone.utc)) < datetime.fromisoformat(receipt.expires_at)
