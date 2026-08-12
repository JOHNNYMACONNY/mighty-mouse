from unittest.mock import Mock

from eval.mutation_engine import MutationEngine
from eval.policy_mutation_engine import MutationAttempt, PolicyMutationEngine
from mighty_mouse.v2.seams import (
    Candidate,
    PolicyMutationSurface,
    VerificationResult,
)
from test_utils import isolated_engine_paths


def _candidate() -> Candidate:
    return Candidate(
        candidate_id="c_base",
        generation_id="g_1",
        mode="coding",
        policy_data={"rules": "base_rules"},
        status="evaluating",
    )


def _verification(*, passed: bool) -> VerificationResult:
    return VerificationResult(
        passed=passed,
        score=1.0 if passed else 0.25,
        details={"verifier_category": "LOGIC"},
        verdict_category="PASS" if passed else "FAIL",
    )


def _isolated_policy_engine(tmp_path) -> PolicyMutationEngine:
    paths = isolated_engine_paths(tmp_path)
    engine = PolicyMutationEngine(
        segments_dir=paths["segments_dir"],
        agent_config=paths["agent_config"],
    )
    return engine


def test_policy_mutation_engine_applies_allowed_mutation(
    monkeypatch, tmp_path
) -> None:
    engine = _isolated_policy_engine(tmp_path)
    monkeypatch.setattr(
        engine,
        "generate_mutation",
        lambda category, failures: (
            "reasoning.txt",
            MutationAttempt("reasoning.txt", "Improve logic", "new rules"),
        ),
    )

    mutated = engine.mutate_candidate(
        _candidate(),
        _verification(passed=False),
        PolicyMutationSurface(frozenset({"reasoning.txt"})),
    )

    assert mutated.candidate_id == "c_base_m"
    assert mutated.policy_data == {
        "rules": "base_rules",
        "reasoning.txt": "new rules",
        "mutation_hypothesis": "Improve logic",
    }
    assert mutated.status == "pending"


def test_policy_mutation_engine_preserves_noop_and_reject(
    monkeypatch, tmp_path
) -> None:
    engine = _isolated_policy_engine(tmp_path)
    generator = Mock(
        return_value=(
            "constraints.txt",
            MutationAttempt(
                "constraints.txt", "Change scope", "new constraints"
            ),
        )
    )
    monkeypatch.setattr(engine, "generate_mutation", generator)
    surface = PolicyMutationSurface(frozenset({"reasoning.txt"}))

    passed = engine.mutate_candidate(
        _candidate(), _verification(passed=True), surface
    )
    rejected = engine.mutate_candidate(
        _candidate(), _verification(passed=False), surface
    )

    assert passed.policy_data == {"rules": "base_rules"}
    assert rejected.policy_data == {"rules": "base_rules"}
    assert generator.call_count == 1


def test_legacy_mutation_engine_delegates_typed_candidate_mutation(
    tmp_path,
) -> None:
    delegate = Mock()
    expected = _candidate()
    delegate.mutate_candidate.return_value = expected
    engine = MutationEngine(**isolated_engine_paths(
        tmp_path,
        policy_mutation_engine=delegate,
    ))
    candidate = _candidate()
    verification = _verification(passed=False)
    surface = PolicyMutationSurface(frozenset({"reasoning.txt"}))

    result = engine.mutate_candidate(candidate, verification, surface)

    assert result is expected
    delegate.mutate_candidate.assert_called_once_with(
        candidate, verification, surface
    )


def test_legacy_mutation_engine_defaults_to_canonical_engine(tmp_path) -> None:
    engine = MutationEngine(**isolated_engine_paths(tmp_path))

    assert isinstance(engine.policy_mutation_engine, PolicyMutationEngine)


def test_legacy_mutation_engine_delegates_generation(tmp_path) -> None:
    delegate = Mock()
    expected = (
        "reasoning.txt",
        MutationAttempt("reasoning.txt", "Improve logic", "new rules"),
    )
    delegate.generate_mutation.return_value = expected
    engine = MutationEngine(**isolated_engine_paths(
        tmp_path,
        policy_mutation_engine=delegate,
    ))
    failures = [{"task_id": "t1", "reason": "logic error"}]

    result = engine.generate_mutation("LOGIC", failures)

    assert result == expected
    delegate.generate_mutation.assert_called_once_with("LOGIC", failures)
