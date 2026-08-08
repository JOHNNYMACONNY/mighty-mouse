from dataclasses import asdict, dataclass
from datetime import datetime
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Literal,
    Optional,
    Tuple,
)

try:
    from .policy_mutation_engine import MutationAttempt, _allowed_segments
except ImportError:
    from policy_mutation_engine import MutationAttempt, _allowed_segments

if TYPE_CHECKING:
    from mighty_mouse.v2.seams import VerificationResult


@dataclass(frozen=True)
class FailureAnalysis:
    dominant_category: str
    is_timeout_dominant: bool
    failures: List[Dict[str, Any]]
    original_summary: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class MutationLogRecord:
    timestamp: str
    failure_category: str
    segment_changed: str
    hypothesis: str
    before: Optional[Dict[str, Any]]
    after: Optional[Dict[str, Any]]
    replay_tiers_tested: List[str]
    decision: Literal[
        "PROMOTE",
        "REJECT",
        "FROZEN_TIMEOUT",
        "FAILED_GENERATION",
    ]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MutationCycleCoordinator:
    def __init__(
        self,
        *,
        analyze_failures: Callable[[], Optional[FailureAnalysis]],
        generate_mutation: Callable[
            [str, List[Dict[str, Any]]],
            Tuple[Optional[str], Optional[MutationAttempt]],
        ],
        run_tier: Callable[[str], Optional[Dict[str, Any]]],
        get_pass_rate: Callable[[Optional[Dict[str, Any]]], float],
        log_mutation: Callable[[MutationLogRecord], None],
        read_segment: Callable[[str], str],
        write_segment: Callable[[str, str], None],
    ) -> None:
        self.analyze_failures = analyze_failures
        self.generate_mutation = generate_mutation
        self.run_tier = run_tier
        self.get_pass_rate = get_pass_rate
        self.log_mutation = log_mutation
        self.read_segment = read_segment
        self.write_segment = write_segment

    def run(
        self,
        *,
        current_tier: str,
        replay_tiers: List[str],
        mutation_surface: Optional[object] = None,
        verification_result: Optional["VerificationResult"] = None,
    ) -> Optional[MutationLogRecord]:
        if verification_result is not None:
            category = str(
                verification_result.details.get("verifier_category", "LOGIC")
            ).upper()
            analysis = (
                FailureAnalysis(
                    dominant_category=category,
                    is_timeout_dominant=category == "TIMEOUT",
                    failures=[
                        {
                            "task_id": current_tier,
                            "reason": "typed verification failure",
                            "category": category,
                        }
                    ],
                    original_summary={
                        "success_rate": (
                            f"{round(verification_result.score * 100)}/100"
                        )
                    },
                )
                if not verification_result.passed
                else None
            )
        else:
            analysis = self.analyze_failures()
        if not analysis:
            print("[*] No failures to analyze. Exiting.")
            return None

        if analysis.is_timeout_dominant:
            print(
                "[!] TIMEOUT detected as dominant failure mode "
                "(Gemma 4 Reasoning Horizon reached)."
            )
            print(
                "[!] FREEZING mutations to reasoning.txt and discipline.txt."
            )
            record = MutationLogRecord(
                timestamp=datetime.now().isoformat(),
                failure_category=analysis.dominant_category,
                segment_changed="none",
                hypothesis=(
                    "Mutations frozen due to dominant timeout failure mode."
                ),
                before=analysis.original_summary,
                after=None,
                replay_tiers_tested=replay_tiers,
                decision="FROZEN_TIMEOUT",
            )
            self.log_mutation(record)
            return record

        segment_file, attempt = self.generate_mutation(
            analysis.dominant_category,
            analysis.failures,
        )
        if not attempt or not segment_file:
            record = MutationLogRecord(
                timestamp=datetime.now().isoformat(),
                failure_category=analysis.dominant_category,
                segment_changed=segment_file or "unknown",
                hypothesis="Mutation generation failed.",
                before=analysis.original_summary,
                after=None,
                replay_tiers_tested=replay_tiers,
                decision="FAILED_GENERATION",
            )
            self.log_mutation(record)
            return record

        allowed_segments = _allowed_segments(mutation_surface)
        if (
            allowed_segments is not None
            and segment_file not in allowed_segments
        ):
            record = MutationLogRecord(
                timestamp=datetime.now().isoformat(),
                failure_category=analysis.dominant_category,
                segment_changed=segment_file,
                hypothesis=(
                    "Mutation rejected because the segment is outside the "
                    "Policy Mutation Surface."
                ),
                before=analysis.original_summary,
                after=None,
                replay_tiers_tested=replay_tiers,
                decision="REJECT",
            )
            self.log_mutation(record)
            return record

        original_content = self.read_segment(segment_file)
        print(f"[*] Applying mutation to {segment_file}...")
        print(f"[*] Hypothesis: {attempt.hypothesis}")
        self.write_segment(segment_file, attempt.new_content)

        new_summary = self.run_tier(current_tier)
        original_rate = self.get_pass_rate(analysis.original_summary)
        new_rate = self.get_pass_rate(new_summary)
        print(
            f"[*] Current Tier Results: {original_rate:.1%} -> {new_rate:.1%}"
        )

        decision: Literal[
            "PROMOTE",
            "REJECT",
            "FROZEN_TIMEOUT",
            "FAILED_GENERATION",
        ] = "REJECT"
        if new_rate >= original_rate:
            decision = "PROMOTE"
            for replay_tier in replay_tiers:
                replay_summary = self.run_tier(replay_tier)
                if self.get_pass_rate(replay_summary) < 0.90:
                    print(
                        f"[!] Mutation failed replay test on {replay_tier}. "
                        "Rejecting."
                    )
                    decision = "REJECT"
                    break

        record = MutationLogRecord(
            timestamp=datetime.now().isoformat(),
            failure_category=analysis.dominant_category,
            segment_changed=segment_file,
            hypothesis=attempt.hypothesis,
            before=analysis.original_summary,
            after=new_summary,
            replay_tiers_tested=replay_tiers,
            decision=decision,
        )

        if decision == "REJECT":
            print("[!] Mutation REJECTED. Restoring segment.")
            self.write_segment(segment_file, original_content)
        else:
            print("[+] Mutation PROMOTED.")

        self.log_mutation(record)
        return record
