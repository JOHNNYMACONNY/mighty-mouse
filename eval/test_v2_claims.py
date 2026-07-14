from datetime import datetime, timedelta, timezone

import pytest

from mighty_mouse.v2.claims import ClaimEvidence, issue_claim, receipt_is_current
from mighty_mouse.v2.evaluation import DevelopmentEvaluator, EvaluationOutcomeKind, FreshHoldoutEvaluator, FreshHoldoutRequest
from mighty_mouse.v2.foundation import EvidenceBundle, ImmutableStateStore
from test_v2_background_research import _controller, _start
from test_v2_evaluation import _request


def _qualifying_claim_evidence(experiment_id, evidence_bundle_id):
    return ClaimEvidence(
        experiment_id=experiment_id,
        evidence_bundle_ids=(evidence_bundle_id,),
        corpus_digest="sha256:corpus",
        evaluator_digest="sha256:evaluator",
        protocol_version="v2",
        protocol_digest="sha256:protocol",
        paired_tasks=30,
        preregistered=True,
        paired_ci_lower=0.2,
        minimum_effect=0.1,
        mcnemar_p=0.01,
        protected_categories_pass=True,
    )


def _held_out_nominee(tmp_path):
    controller = _controller(tmp_path)
    generation_id = _start(controller)["generation_id"]
    controller.run(thermal_state="normal")
    result = DevelopmentEvaluator(tmp_path).evaluate(
        _request(tmp_path, generation_id),
        lambda task_id, candidate, workspace, seed: EvaluationOutcomeKind.PASSED if candidate.policy.version == "generated-1" else EvaluationOutcomeKind.FAILED,
    )
    evaluator = FreshHoldoutEvaluator(tmp_path)
    task_digests = (("fresh-task-001", "sha256:fresh-task"),)
    manifest_digest = evaluator.freeze_manifest(
        task_digests=task_digests,
        corpus_digest="sha256:corpus",
        protocol_digest="sha256:protocol",
        environment_digest="sha256:environment",
    )
    held = evaluator.evaluate(
        FreshHoldoutRequest(
            result.experiment_id, result.holdout_nominee_id, _request(tmp_path, generation_id).base_workspace,
            ("fresh-task-001",), "sha256:protocol", "sha256:environment", "sha256:corpus", task_digests, manifest_digest,
        ),
        lambda task_id, candidate, workspace, seed: EvaluationOutcomeKind.PASSED,
    )
    return result, held


def test_tier_two_claim_uses_matching_protocol_digest_and_remains_current(tmp_path):
    result, held = _held_out_nominee(tmp_path)
    receipt = issue_claim(
        state_dir=tmp_path,
        wording="Scoped comparative claim",
        tier=2,
        candidate_id=held.candidate_id,
        model_identity="sha256:model",
        execution_profile="codex-local",
        evidence=_qualifying_claim_evidence(result.experiment_id, held.evidence_bundle_id),
        expires_at=datetime.now(timezone.utc) + timedelta(days=1),
    )

    assert receipt.protocol_digest == "sha256:protocol"
    assert receipt_is_current(receipt, state_dir=tmp_path)


def test_claim_rejects_missing_or_unrelated_evidence_bundle(tmp_path):
    result, held = _held_out_nominee(tmp_path)
    evidence = _qualifying_claim_evidence(result.experiment_id, held.evidence_bundle_id)
    ImmutableStateStore(tmp_path).append(EvidenceBundle("evidence-unrelated", "experiment-other", "sha256:model", "codex-local", "sha256:unrelated"))

    with pytest.raises(ValueError, match="evidence bundles"):
        issue_claim(
            state_dir=tmp_path, wording="Scoped comparative claim", tier=2, candidate_id=held.candidate_id,
            model_identity="sha256:model", execution_profile="codex-local",
            evidence=ClaimEvidence(**{**evidence.__dict__, "evidence_bundle_ids": (held.evidence_bundle_id, "evidence-unrelated")}),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )


def test_claim_rejects_a_protocol_version_that_does_not_match_its_experiment(tmp_path):
    result, held = _held_out_nominee(tmp_path)
    evidence = _qualifying_claim_evidence(result.experiment_id, held.evidence_bundle_id)

    with pytest.raises(ValueError, match="protocol version"):
        issue_claim(
            state_dir=tmp_path, wording="Scoped comparative claim", tier=2, candidate_id=held.candidate_id,
            model_identity="sha256:model", execution_profile="codex-local",
            evidence=ClaimEvidence(**{**evidence.__dict__, "protocol_version": "v3"}),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )


def test_claim_rejects_a_conflicting_duplicate_evidence_bundle(tmp_path):
    result, held = _held_out_nominee(tmp_path)
    ImmutableStateStore(tmp_path).append(EvidenceBundle(held.evidence_bundle_id, result.experiment_id, "sha256:model", "codex-local", "sha256:conflict", held.candidate_id))

    with pytest.raises(ValueError, match="evidence bundles"):
        issue_claim(
            state_dir=tmp_path, wording="Scoped comparative claim", tier=2, candidate_id=held.candidate_id,
            model_identity="sha256:model", execution_profile="codex-local",
            evidence=_qualifying_claim_evidence(result.experiment_id, held.evidence_bundle_id),
            expires_at=datetime.now(timezone.utc) + timedelta(days=1),
        )
