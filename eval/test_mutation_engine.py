import json
import os
import tempfile
import pytest
from unittest.mock import MagicMock, patch

from mutation_engine import (
    MutationEngine,
    FailureAnalysis,
    MutationAttempt,
    ProtocolManifest,
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
    manifest = engine.execute_mutation_cycle(current_tier="tier-1", replay_tiers=[])
    
    assert manifest is not None
    assert manifest.decision == "FROZEN_TIMEOUT"
    assert os.path.exists(mutation_log_path)


def test_protocol_manifest_serialization():
    manifest = ProtocolManifest(
        timestamp="2026-07-28T20:00:00",
        failure_category="LOGIC",
        segment_changed="reasoning.txt",
        hypothesis="Improve step validation",
        before={"success_rate": "5/10"},
        after={"success_rate": "8/10"},
        replay_tiers_tested=["tier-1"],
        decision="PROMOTE"
    )
    d = manifest.to_dict()
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
