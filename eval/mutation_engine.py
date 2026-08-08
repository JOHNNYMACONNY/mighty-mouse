import json
import os
import subprocess
import sys
from datetime import datetime
from typing import TYPE_CHECKING, Dict, Any, List, Optional, Tuple

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
if _EVAL_DIR not in sys.path: sys.path.append(_EVAL_DIR)
if _REPO_ROOT not in sys.path: sys.path.append(_REPO_ROOT)
sys.path.append(os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator"))

from tier_utils import load_tier_sequence, get_current_tier as utils_get_current_tier, parse_pass_rate
from gemini_client import GeminiClient  # noqa: E402

try:
    from .policy_mutation_engine import (  # noqa: F401
        AGENT_CONFIG,
        CATEGORY_TO_SEGMENT,
        MutationAttempt,
        PolicyMutationEngine,
        SEGMENTS_DIR,
        _allowed_segments,
    )  # noqa: F401
except ImportError:
    from policy_mutation_engine import (  # noqa: F401
        AGENT_CONFIG,
        CATEGORY_TO_SEGMENT,
        MutationAttempt,
        PolicyMutationEngine,
        SEGMENTS_DIR,
        _allowed_segments,
    )  # noqa: F401

try:
    from .mutation_cycle import (
        FailureAnalysis,
        MutationCycleCoordinator,
        MutationLogRecord,
    )
except ImportError:
    from mutation_cycle import (
        FailureAnalysis,
        MutationCycleCoordinator,
        MutationLogRecord,
    )

if TYPE_CHECKING:
    from mighty_mouse.v2.seams import Candidate, VerificationResult

# Default Configuration Constants
RESULTS_PATH = "eval/results/benchmark_results.json"
MUTATION_LOG_PATH = "logs/mutation_log.jsonl"
TIERS = load_tier_sequence()

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


class MutationEngine:
    """Legacy mutation-loop orchestration and compatibility adapter."""

    def __init__(
        self,
        results_path: str = RESULTS_PATH,
        mutation_log_path: str = MUTATION_LOG_PATH,
        segments_dir: str = SEGMENTS_DIR,
        agent_config: str = AGENT_CONFIG,
        policy_mutation_engine: Optional[PolicyMutationEngine] = None,
    ):
        self.results_path = results_path
        self.mutation_log_path = mutation_log_path
        self.segments_dir = segments_dir
        self.agent_config = agent_config
        self.policy_mutation_engine = (
            policy_mutation_engine
            if policy_mutation_engine is not None
            else PolicyMutationEngine(
                segments_dir=segments_dir,
                agent_config=agent_config,
                client_factory=GeminiClient,
            )
        )

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
        """Delegate mutation generation to canonical PolicyMutationEngine."""
        return self.policy_mutation_engine.generate_mutation(
            category, failures
        )

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

    def _read_segment(self, segment_file: str) -> str:
        segment_path = os.path.join(self.segments_dir, segment_file)
        with open(segment_path, 'r') as f:
            return f.read()

    def _write_segment(self, segment_file: str, content: str) -> None:
        segment_path = os.path.join(self.segments_dir, segment_file)
        with open(segment_path, 'w') as f:
            f.write(content)

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
        coordinator = MutationCycleCoordinator(
            analyze_failures=self.analyze_failures,
            generate_mutation=self.generate_mutation,
            run_tier=self.run_tier,
            get_pass_rate=self.get_pass_rate,
            log_mutation=self.log_mutation,
            read_segment=self._read_segment,
            write_segment=self._write_segment,
        )
        return coordinator.run(
            current_tier=current_tier,
            replay_tiers=replay_tiers,
            mutation_surface=mutation_surface,
            verification_result=verification_result,
        )

    def mutate_candidate(
        self,
        candidate: "Candidate",
        verification: "VerificationResult",
        mutation_surface: Optional[Dict[str, Any]] = None,
    ) -> "Candidate":
        """Delegate typed Candidate mutation to canonical engine."""
        return self.policy_mutation_engine.mutate_candidate(
            candidate, verification, mutation_surface
        )




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
