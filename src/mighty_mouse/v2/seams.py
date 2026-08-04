"""
Seams and Protocol Interfaces for Mighty Mouse v2.

Defines explicit boundary layers (seams) for evaluation, mutation,
and verification, enforcing deep module principles.
"""

from __future__ import annotations

from typing import Protocol, Mapping, Optional, Literal
from dataclasses import dataclass

CandidateStatus = Literal["pending", "evaluating", "pass", "fail"]
SignalOutcome = Literal["pass", "fail", "error"]
VerifierCategory = Literal["SCOPE", "ADHERENCE", "LOGIC", "VERIFICATION", "REGRESSION", "EFFICIENCY", "PARSER", "TIMEOUT"]
VerdictCategory = Literal["PASS", "FAIL", "ERROR"]

@dataclass(frozen=True)
class Candidate:
    """Immutable policy candidate undergoing evaluation."""
    candidate_id: str
    generation_id: str
    mode: str
    policy_data: Mapping[str, str]
    status: CandidateStatus = "pending"


@dataclass(frozen=True)
class Signal:
    """Structured observation from routine evaluation or use."""
    signal_id: str
    candidate_id: str
    outcome: SignalOutcome
    duration_ms: float
    verifier_category: VerifierCategory


@dataclass(frozen=True)
class PolicyMutationSurface:
    """Explicit allowlist for Candidate policy segments a mutation may change."""

    allowed_segments: frozenset[str]


@dataclass(frozen=True)
class VerificationResult:
    """Deterministic output from a verifier seam execution."""
    passed: bool
    score: float
    details: Mapping[str, str | int | float | bool]
    verdict_category: VerdictCategory


class PolicyMutationAdapter(Protocol):
    """Deep seam for applying controlled mutations to a Candidate."""

    def mutate_candidate(
        self,
        candidate: Candidate,
        verification: VerificationResult,
        mutation_surface: Optional[PolicyMutationSurface] = None,
    ) -> Candidate:
        """Apply typed verification feedback and return a new immutable Candidate."""
        ...


# Type alias for Spec compliance
PolicyMutationEngine = PolicyMutationAdapter


class EvaluationHarnessAdapter(Protocol):
    """Deep seam for driving autonomous candidate evaluation loops."""

    def run_evaluation_cycle(
        self, candidate: Candidate, suite_name: str
    ) -> VerificationResult:
        """Executes candidate against a specified test or benchmark suite."""
        ...

    def expand_benchmark_suite(self, suite_name: str) -> bool:
        """Expands the evaluation suite to higher difficulty tier upon baseline pass."""
        ...


class VerifierAdapter(Protocol):
    """Seam for deterministic verification execution."""

    def verify(
        self, candidate: Candidate, test_scope: str
    ) -> VerificationResult:
        """Performs empirical verification against candidate output or behavior."""
        ...
