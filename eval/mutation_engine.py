import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Any, List, Mapping, Optional, Tuple, Literal
import yaml

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
if _EVAL_DIR not in sys.path: sys.path.append(_EVAL_DIR)
if _REPO_ROOT not in sys.path: sys.path.append(_REPO_ROOT)
sys.path.append(os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))

from gemini_client import GeminiClient
from tier_utils import load_tier_sequence, get_current_tier as utils_get_current_tier, parse_pass_rate

if TYPE_CHECKING:
    from mighty_mouse.v2.seams import Candidate, VerificationResult

# Default Configuration Constants
RESULTS_PATH = "eval/results/benchmark_results.json"
MUTATION_LOG_PATH = "logs/mutation_log.jsonl"
SEGMENTS_DIR = "configs/prompt_segments"
AGENT_CONFIG = "configs/mighty_mouse_v1.yaml"
TIERS = load_tier_sequence()

CATEGORY_TO_SEGMENT = {
    "SCOPE": "constraints.txt",
    "ADHERENCE": "discipline.txt",
    "LOGIC": "reasoning.txt",
    "VERIFICATION": "verification.txt",
    "REGRESSION": "discipline.txt",
    "EFFICIENCY": "reasoning.txt",
    "PARSER": "constraints.txt",
    "TIMEOUT": "timeout_policy"
}


def _allowed_segments(mutation_surface: object) -> frozenset[str] | None:
    if mutation_surface is None:
        return None
    if isinstance(mutation_surface, Mapping):
        return mutation_surface.get("allowed_segments")
    return getattr(mutation_surface, "allowed_segments", None)

def get_current_tier() -> str:
    return utils_get_current_tier()

def get_replay_tiers(current_tier: str) -> List[str]:
    tiers = load_tier_sequence()
    if current_tier not in tiers:
        return []
    idx = tiers.index(current_tier)
    replays = []
    if idx > 0:
        replays.append(tiers[idx-1])
    if idx > 1:
        replays.append(tiers[idx-2])
    return replays


@dataclass(frozen=True)
class FailureAnalysis:
    dominant_category: str
    is_timeout_dominant: bool
    failures: List[Dict[str, Any]]
    original_summary: Optional[Dict[str, Any]]


@dataclass(frozen=True)
class MutationAttempt:
    segment_file: str
    hypothesis: str
    new_content: str


@dataclass(frozen=True)
class MutationLogRecord:
    timestamp: str
    failure_category: str
    segment_changed: str
    hypothesis: str
    before: Optional[Dict[str, Any]]
    after: Optional[Dict[str, Any]]
    replay_tiers_tested: List[str]
    decision: Literal["PROMOTE", "REJECT", "FROZEN_TIMEOUT", "FAILED_GENERATION"]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MutationEngine:
    """Typed in-process engine for prompt mutation generation, evaluation, and promotion."""

    def __init__(
        self,
        results_path: str = RESULTS_PATH,
        mutation_log_path: str = MUTATION_LOG_PATH,
        segments_dir: str = SEGMENTS_DIR,
        agent_config: str = AGENT_CONFIG,
    ):
        self.results_path = results_path
        self.mutation_log_path = mutation_log_path
        self.segments_dir = segments_dir
        self.agent_config = agent_config

    def analyze_failures(self) -> Optional[FailureAnalysis]:
        if not os.path.exists(self.results_path):
            return None
        with open(self.results_path, 'r') as f:
            data = json.load(f)
        
        results = data.get("results", [])
        failures = [r for r in results if r.get("status") == "fail"]
        if not failures:
            return None
        
        counts: Dict[str, int] = {}
        for f in failures:
            cat = f.get("category", "LOGIC")
            counts[cat] = counts.get(cat, 0) + 1
        
        dominant = max(counts, key=counts.get) # type: ignore
        is_timeout_dominant = (dominant == "TIMEOUT") or (counts.get("TIMEOUT", 0) >= 2)
        
        return FailureAnalysis(
            dominant_category=dominant,
            is_timeout_dominant=is_timeout_dominant,
            failures=failures,
            original_summary=data.get("summary")
        )

    def generate_mutation(self, category: str, failures: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[MutationAttempt]]:
        segment_file = CATEGORY_TO_SEGMENT.get(category, "reasoning.txt")
        segment_path = os.path.join(self.segments_dir, segment_file)
        
        if not os.path.exists(segment_path):
            return segment_file, None

        with open(segment_path, 'r') as f:
            current_content = f.read()
        
        examples = "\n".join([f"- Task: {f['task_id']}, Reason: {f.get('reason', '')}" for f in failures[:3]])
        
        prompt = f"""
You are a Prompt Engineering Expert for the Mighty Mouse project.
We are seeing failures in the category: {category}.
Representative failures:
{examples}

Current content of '{segment_file}':
{current_content}

Your goal is to provide a MINIMAL mutation to this segment to address these failures without breaking existing behavior.
Output your response in this JSON format:
{{
  "hypothesis": "Your specific hypothesis on why this change will help",
  "new_content": "The full new content for the segment"
}}
"""
        if not os.path.exists(self.agent_config):
            return segment_file, None

        with open(self.agent_config, 'r') as f:
            cfg = yaml.safe_load(f)
        
        client = GeminiClient(config=cfg)
        try:
            response_text = client.generate_content("You are a prompt engineering expert.", prompt)
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "{" in response_text:
                response_text = response_text[response_text.find("{"):response_text.rfind("}")+1]
            
            mutation_data = json.loads(response_text)
            attempt = MutationAttempt(
                segment_file=segment_file,
                hypothesis=mutation_data.get("hypothesis", ""),
                new_content=mutation_data.get("new_content", "")
            )
            return segment_file, attempt
        except Exception as e:
            print(f"[!] Mutation generation failed: {e}")
            return segment_file, None

    def run_tier(self, tier: str) -> Optional[Dict[str, Any]]:
        print(f"[*] Testing tier: {tier}...")
        cmd = [sys.executable, "eval/solve_benchmark.py", "--tier", tier]
        subprocess.run(
            cmd,
            capture_output=True,
            env={**os.environ, "MIGHTY_MOUSE_RUNNER_LOCK_HELD": "1"},
        )
        if os.path.exists(self.results_path):
            with open(self.results_path, 'r') as f:
                return json.load(f).get("summary")
        return None

    def get_pass_rate(self, summary: Optional[Dict[str, Any]]) -> float:
        return parse_pass_rate(summary)

    def log_mutation(self, record: MutationLogRecord) -> None:
        log_dir = os.path.dirname(self.mutation_log_path)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)
        with open(self.mutation_log_path, 'a') as f:
            f.write(json.dumps(record.to_dict()) + "\n")

    def execute_mutation_cycle(
        self,
        current_tier: Optional[str] = None,
        replay_tiers: Optional[List[str]] = None,
        mutation_surface: Optional[Dict[str, Any]] = None,
        verification_result: Optional["VerificationResult"] = None,
    ) -> Optional[MutationLogRecord]:
        print("=== Mighty Mouse Mutation Engine Starting ===")
        if current_tier is None:
            current_tier = get_current_tier()
        if replay_tiers is None:
            replay_tiers = get_replay_tiers(current_tier)
        if verification_result is not None:
            category = str(verification_result.details.get("verifier_category", "LOGIC")).upper()
            analysis = FailureAnalysis(
                dominant_category=category,
                is_timeout_dominant=category == "TIMEOUT",
                failures=[
                    {
                        "task_id": current_tier,
                        "reason": "typed verification failure",
                        "category": category,
                    }
                ],
                original_summary={"success_rate": f"{round(verification_result.score * 100)}/100"},
            ) if not verification_result.passed else None
        else:
            analysis = self.analyze_failures()
        if not analysis:
            print("[*] No failures to analyze. Exiting.")
            return None

        if analysis.is_timeout_dominant:
            print("[!] TIMEOUT detected as dominant failure mode (Gemma 4 Reasoning Horizon reached).")
            print("[!] FREEZING mutations to reasoning.txt and discipline.txt.")
            record = MutationLogRecord(
                timestamp=datetime.now().isoformat(),
                failure_category=analysis.dominant_category,
                segment_changed="none",
                hypothesis="Mutations frozen due to dominant timeout failure mode.",
                before=analysis.original_summary,
                after=None,
                replay_tiers_tested=replay_tiers,
                decision="FROZEN_TIMEOUT",
            )
            self.log_mutation(record)
            return record

        segment_file, attempt = self.generate_mutation(analysis.dominant_category, analysis.failures)
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

        segment_path = os.path.join(self.segments_dir, segment_file)
        allowed_segments = _allowed_segments(mutation_surface)
        if allowed_segments is not None and segment_file not in allowed_segments:
            record = MutationLogRecord(
                timestamp=datetime.now().isoformat(),
                failure_category=analysis.dominant_category,
                segment_changed=segment_file,
                hypothesis="Mutation rejected because the segment is outside the Policy Mutation Surface.",
                before=analysis.original_summary,
                after=None,
                replay_tiers_tested=replay_tiers,
                decision="REJECT",
            )
            self.log_mutation(record)
            return record
        with open(segment_path, 'r') as f:
            original_content = f.read()
        
        print(f"[*] Applying mutation to {segment_file}...")
        print(f"[*] Hypothesis: {attempt.hypothesis}")
        
        with open(segment_path, 'w') as f:
            f.write(attempt.new_content)
        
        new_summary = self.run_tier(current_tier)
        original_rate = self.get_pass_rate(analysis.original_summary)
        new_rate = self.get_pass_rate(new_summary)
        
        print(f"[*] Current Tier Results: {original_rate:.1%} -> {new_rate:.1%}")
        
        decision: Literal["PROMOTE", "REJECT", "FROZEN_TIMEOUT", "FAILED_GENERATION"] = "REJECT"
        if new_rate >= original_rate:
            decision = "PROMOTE"
            for rt in replay_tiers:
                rt_summary = self.run_tier(rt)
                if self.get_pass_rate(rt_summary) < 0.90:
                    print(f"[!] Mutation failed replay test on {rt}. Rejecting.")
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
            decision=decision
        )
        
        if decision == "REJECT":
            print("[!] Mutation REJECTED. Restoring segment.")
            with open(segment_path, 'w') as f:
                f.write(original_content)
        else:
            print("[+] Mutation PROMOTED.")
        
        self.log_mutation(record)

        return record

    def mutate_candidate(
        self,
        candidate: "Candidate",
        verification: "VerificationResult",
        mutation_surface: Optional[Dict[str, Any]] = None,
    ) -> "Candidate":
        """Deep seam interface implementation of PolicyMutationAdapter."""
        from mighty_mouse.v2.seams import Candidate as V2Candidate

        policy_data = dict(candidate.policy_data)
        if hasattr(verification, "details"):
            category = str(verification.details.get("verifier_category", "LOGIC"))
            failures = [] if verification.passed else [{"task_id": candidate.candidate_id, "reason": "typed verification failure"}]
        else:
            category = str(getattr(verification, "verifier_category", "LOGIC"))
            failures = []

        segment_file, attempt = (None, None)
        if failures:
            segment_file, attempt = self.generate_mutation(category, failures)
        if attempt:
            # Respect mutation_surface if provided
            allowed_segments = _allowed_segments(mutation_surface)
            if allowed_segments is None or segment_file in allowed_segments:
                policy_data[segment_file] = attempt.new_content
                policy_data["mutation_hypothesis"] = attempt.hypothesis

        cand_id = f"{candidate.candidate_id}_m"
        return V2Candidate(
            candidate_id=cand_id,
            generation_id=candidate.generation_id,
            mode=candidate.mode,
            policy_data=policy_data,
            status="pending",
        )


# Class alias for Spec compliance
PolicyMutationEngine = MutationEngine




# Module-level convenience functions for backward compatibility
def analyze_failures() -> Optional[Tuple[str, bool, List[Dict[str, Any]], Optional[Dict[str, Any]]]]:
    engine = MutationEngine()
    res = engine.analyze_failures()
    if not res:
        return None
    return res.dominant_category, res.is_timeout_dominant, res.failures, res.original_summary

def generate_mutation(category: str, failures: List[Dict[str, Any]]) -> Tuple[Optional[str], Optional[Dict[str, str]]]:
    engine = MutationEngine()
    seg, attempt = engine.generate_mutation(category, failures)
    if not attempt:
        return seg, None
    return seg, {"hypothesis": attempt.hypothesis, "new_content": attempt.new_content}

def run_tier(tier: str) -> Optional[Dict[str, Any]]:
    return MutationEngine().run_tier(tier)

def get_pass_rate(summary: Optional[Dict[str, Any]]) -> float:
    return MutationEngine().get_pass_rate(summary)

def log_mutation(record: Dict[str, Any]) -> None:
    log_record = MutationLogRecord(
        timestamp=record.get("timestamp", datetime.now().isoformat()),
        failure_category=record.get("failure_category", "LOGIC"),
        segment_changed=record.get("segment_changed", ""),
        hypothesis=record.get("hypothesis", ""),
        before=record.get("before"),
        after=record.get("after"),
        replay_tiers_tested=record.get("replay_tiers_tested", []),
        decision=record.get("decision", "REJECT")
    )
    MutationEngine().log_mutation(log_record)

def main() -> None:
    engine = MutationEngine()
    engine.execute_mutation_cycle()

if __name__ == "__main__":
    main()
