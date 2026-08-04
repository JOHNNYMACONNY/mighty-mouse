import json
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from mutation_engine import (
    MutationEngine,
    FailureAnalysis,
    MutationAttempt,
    MutationLogRecord,
    CATEGORY_TO_SEGMENT,
)
from perpetual_loop import AutoresearchLoop, AtomicState


def test_failure_analysis_no_file(tmp_path):
    results_path = str(tmp_path / "nonexistent.json")
    engine = MutationEngine(results_path=results_path)
    analysis = engine.analyze_failures()
    assert analysis is None


def test_failure_analysis_parsing(tmp_path):
    results_path = str(tmp_path / "benchmark_results.json")
    data = {
        "summary": {"success_rate": "1/3"},
        "results": [
            {"task_id": "t1", "status": "pass"},
            {"task_id": "t2", "status": "fail", "category": "SCOPE", "reason": "out of bounds"},
            {"task_id": "t3", "status": "fail", "category": "SCOPE", "reason": "invalid path"},
        ]
    }
    with open(results_path, "w") as f:
        json.dump(data, f)

    engine = MutationEngine(results_path=results_path)
    analysis = engine.analyze_failures()
    assert analysis is not None
    assert analysis.dominant_category == "SCOPE"
    assert analysis.is_timeout_dominant is False
    assert len(analysis.failures) == 2


def test_timeout_dominance_freeze(tmp_path):
    results_path = str(tmp_path / "benchmark_results.json")
    mutation_log_path = str(tmp_path / "mutation_log.jsonl")
    data = {
        "summary": {"success_rate": "0/2"},
        "results": [
            {"task_id": "t1", "status": "fail", "category": "TIMEOUT", "reason": "time limit"},
            {"task_id": "t2", "status": "fail", "category": "TIMEOUT", "reason": "time limit"},
        ]
    }
    with open(results_path, "w") as f:
        json.dump(data, f)

    engine = MutationEngine(results_path=results_path, mutation_log_path=mutation_log_path)
    record = engine.execute_mutation_cycle(current_tier="tier-1", replay_tiers=[])

    assert record is not None
    assert record.decision == "FROZEN_TIMEOUT"
    assert os.path.exists(mutation_log_path)


def test_generate_mutation_mocked_gemini(tmp_path):
    agent_config = str(tmp_path / "agent.yaml")
    segments_dir = str(tmp_path / "segments")
    os.makedirs(segments_dir, exist_ok=True)
    segment_file = str(tmp_path / "segments" / "constraints.txt")
    with open(segment_file, "w") as f:
        f.write("Original constraint content")

    with open(agent_config, "w") as f:
        f.write("model: gemma\n")

    failures = [{"task_id": "t1", "reason": "failed constraints"}]

    mock_client = MagicMock()
    mock_client.generate_content.return_value = json.dumps({
        "hypothesis": "Refine strict boundaries",
        "new_content": "Updated constraint content"
    })

    with patch("mutation_engine.GeminiClient", return_value=mock_client):
        engine = MutationEngine(segments_dir=segments_dir, agent_config=agent_config)
        seg, attempt = engine.generate_mutation("SCOPE", failures)
        assert seg == "constraints.txt"
        assert attempt is not None
        assert attempt.hypothesis == "Refine strict boundaries"
        assert attempt.new_content == "Updated constraint content"


def test_execute_mutation_cycle_promote_and_reject_replay(tmp_path):
    results_path = str(tmp_path / "benchmark_results.json")
    mutation_log_path = str(tmp_path / "mutation_log.jsonl")
    segments_dir = str(tmp_path / "segments")
    os.makedirs(segments_dir, exist_ok=True)
    with open(os.path.join(segments_dir, "reasoning.txt"), "w") as f:
        f.write("Original reasoning")

    agent_config = str(tmp_path / "agent.yaml")
    with open(agent_config, "w") as f:
        f.write("model: gemma\n")

    initial_data = {
        "summary": {"success_rate": "1/2"},
        "results": [
            {"task_id": "t1", "status": "fail", "category": "LOGIC", "reason": "logic error"}
        ]
    }
    with open(results_path, "w") as f:
        json.dump(initial_data, f)

    engine = MutationEngine(
        results_path=results_path,
        mutation_log_path=mutation_log_path,
        segments_dir=segments_dir,
        agent_config=agent_config,
    )

    mock_attempt = MutationAttempt(
        segment_file="reasoning.txt",
        hypothesis="Fix logic reasoning step",
        new_content="New reasoning content"
    )

    # Test rejection due to lower replay tier score
    with patch.object(engine, "generate_mutation", return_value=("reasoning.txt", mock_attempt)), \
         patch.object(engine, "run_tier", side_effect=[{"success_rate": "2/2"}, {"success_rate": "1/2"}]):
        record = engine.execute_mutation_cycle(current_tier="tier-2", replay_tiers=["tier-1"])
        assert record is not None
        assert record.decision == "REJECT"
        # Verify segment restored after rejection
        with open(os.path.join(segments_dir, "reasoning.txt"), "r") as f:
            assert f.read() == "Original reasoning"


def test_mutation_log_record_serialization():
    record = MutationLogRecord(
        timestamp="2026-07-28T20:00:00",
        failure_category="LOGIC",
        segment_changed="reasoning.txt",
        hypothesis="Improve step validation",
        before={"success_rate": "5/10"},
        after={"success_rate": "8/10"},
        replay_tiers_tested=["tier-1"],
        decision="PROMOTE"
    )
    d = record.to_dict()
    assert d["decision"] == "PROMOTE"
    assert d["failure_category"] == "LOGIC"


def test_autoresearch_loop_initialization(tmp_path):
    state_path = str(tmp_path / "state.json")
    telemetry_path = str(tmp_path / "telemetry.json")
    bench_results_path = str(tmp_path / "benchmark_results.json")

    loop = AutoresearchLoop(
        state_path=state_path,
        telemetry_path=telemetry_path,
        benchmark_results_path=bench_results_path,
    )
    assert loop.state["mutation_count"] == 0
    assert "current_tier" in loop.state


def test_mutate_candidate_seam():
    from mighty_mouse.v2.seams import Candidate, Signal
    engine = MutationEngine()

    candidate = Candidate(
        candidate_id="c_base",
        generation_id="g_1",
        mode="coding",
        policy_data={"rules": "base_rules"},
        status="evaluating"
    )
    signal = Signal(
        signal_id="sig_1",
        candidate_id="c_base",
        outcome="fail",
        duration_ms=120.0,
        verifier_category="LOGIC"
    )

    mutated = engine.mutate_candidate(candidate, signal)
    assert mutated.candidate_id == "c_base_m"
    assert mutated.status == "pending"
    assert mutated.generation_id == "g_1"
