"""Tests for eval/reliability_matrix.py and its contract schema."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import threading
from typing import Any
from unittest.mock import MagicMock

import jsonschema
import pytest

from eval.reliability_matrix import (
    ARMS,
    DEFAULT_CONFIG_PATH,
    DEFAULT_CONTRACT_PATH,
    MAX_RECOVERY_ATTEMPTS,
    SCHEMA_VERSION,
    SWARM_CONCURRENCY,
    UsageInstrumentation,
    evaluate_tier_corpus,
    load_contract_schema,
    main,
    run_preflight,
    select_deterministic_task,
    validate_payload_against_schema,
)
from eval.runner_lock import SingleInstanceLock, SingleInstanceLockError


def test_schema_contract_validity() -> None:
    schema = load_contract_schema(DEFAULT_CONTRACT_PATH)
    assert schema["version"] == SCHEMA_VERSION
    assert "definitions" in schema
    assert "trial_record" in schema["definitions"]
    assert "preflight_report" in schema["definitions"]
    assert "run_summary" in schema["definitions"]


def test_trial_record_schema_validation() -> None:
    digest_val = (
        "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"
    )
    valid_record = {
        "identity": {
            "schema_version": SCHEMA_VERSION,
            "experiment_id": "m12-pilot-v1",
            "trial_id": "trial-001",
            "trial_order_index": 0,
            "experiment_base_sha": "97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
            "base_sha": "97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
            "harness_sha": "97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
            "arm": "control_once",
            "replicate": 1,
        },
        "task": {
            "configured_tier": "tier_1",
            "task_id": "task_001",
            "task_file": "task_001_legacy_registry_ratelimiter.json",
            "task_sha256": "a" * 64,
        },
        "provenance": {
            "provider": "ollama",
            "ollama_version": "0.33.2",
            "model": "gemma4:e4b",
            "model_digest": digest_val,
            "agent_config_sha256": "b" * 64,
            "prompt_template_sha256": "c" * 64,
            "execution_profile_id": "default",
            "tool_contract_digest": "d" * 64,
            "runtime_version": "0.4.0",
            "experiment_base_sha": "97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
            "harness_sha": "97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
            "baseline_to_harness_changed_paths": [],
        },
        "execution": {
            "swarm_concurrency": 1,
            "internal_attempts": 1,
            "generation_calls": 1,
            "recovery_enabled": False,
            "recovery_attempt_limit": 1,
            "recovery_attempted": False,
            "recovery_completed": False,
            "recovery_trigger_source": "none",
        },
        "verification": {
            "first_passed": True,
            "first_failure_category": None,
            "terminal_passed": True,
            "terminal_failure_category": None,
            "recovery_eligible": False,
            "recovery_gate_reason": None,
        },
        "cost": {
            "primary_prompt_tokens": 512,
            "primary_completion_tokens": 128,
            "recovery_prompt_tokens": 0,
            "recovery_completion_tokens": 0,
            "total_tokens": 640,
            "wall_latency_seconds": 2.5,
            "model_latency_seconds": 2.1,
        },
        "validity": {
            "provenance_complete": True,
            "token_coverage_complete": True,
            "verifier_completed": True,
            "infrastructure_error": None,
            "trace_artifact_relpath": "traces/trial-001.json",
            "trace_artifact_sha256": "e" * 64,
        },
    }
    validate_payload_against_schema(valid_record, "trial_record")

    # Negative test: invalid arm
    invalid_arm = copy.deepcopy(valid_record)
    invalid_arm["identity"]["arm"] = "unknown_arm"
    with pytest.raises(jsonschema.ValidationError):
        validate_payload_against_schema(invalid_arm, "trial_record")

    # Negative test: recovery ceiling > 1
    invalid_ceiling = copy.deepcopy(valid_record)
    invalid_ceiling["execution"]["recovery_attempt_limit"] = 2
    with pytest.raises(jsonschema.ValidationError):
        validate_payload_against_schema(invalid_ceiling, "trial_record")

    # Negative test: extra field (additionalProperties = false)
    invalid_extra = copy.deepcopy(valid_record)
    invalid_extra["identity"]["rogue_field"] = "bad"
    with pytest.raises(jsonschema.ValidationError):
        validate_payload_against_schema(invalid_extra, "trial_record")


def test_preflight_report_schema_validation() -> None:
    digest_val = (
        "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"
    )
    valid_preflight = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": "m12-test-01",
        "experiment_base_sha": "97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
        "base_sha": "97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
        "harness_sha": "97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
        "baseline_to_harness_changed_paths": [],
        "git_clean": True,
        "runner_lock_acquired": True,
        "schema_valid": True,
        "config_path": "eval/evaluation_config.json",
        "config_sha256": "e" * 64,
        "ollama_server": {
            "host": "http://localhost:11434",
            "available": True,
            "version": "0.33.2",
            "model": "gemma4:e4b",
            "model_digest": digest_val,
        },
        "tiers": [
            {
                "name": "tier_1",
                "is_rollup": False,
                "total_configured": 5,
                "available_tasks": 5,
                "missing_tasks": [],
                "blocked": False,
                "sample_task": "task_001.json",
            },
            {
                "name": "tier_2",
                "is_rollup": True,
                "total_configured": 0,
                "available_tasks": 0,
                "missing_tasks": [],
                "blocked": False,
                "sample_task": None,
            },
        ],
        "arms": [
            {
                "arm_id": "control_once",
                "description": "Bare single execution",
                "execution_mode": "bare_control",
                "recovery_enabled": False,
            }
        ],
        "output_dir": {
            "path": "eval/results/m12/test",
            "writable": True,
            "ready": True,
        },
        "recovery_attempt_ceiling": 1,
        "dry_run": True,
        "generation_calls": 0,
        "preflight_passed": True,
        "blocking_reasons": [],
        "timestamp": "2026-09-02T20:00:00Z",
    }
    validate_payload_against_schema(valid_preflight, "preflight_report")

    # Negative test: generation_calls must be 0 in preflight
    invalid_calls = copy.deepcopy(valid_preflight)
    invalid_calls["generation_calls"] = 1
    with pytest.raises(jsonschema.ValidationError):
        validate_payload_against_schema(invalid_calls, "preflight_report")

    # Negative test: dry_run must be true in preflight
    invalid_dry_run = copy.deepcopy(valid_preflight)
    invalid_dry_run["dry_run"] = False
    with pytest.raises(jsonschema.ValidationError):
        validate_payload_against_schema(invalid_dry_run, "preflight_report")


def test_deterministic_task_selector() -> None:
    base_sha = "97d3dd5f3d663aa76d241f33ae606fd1c7668e94"
    tasks = [f"task_{i:03d}.json" for i in range(10)]

    # Repeatability
    sample1 = select_deterministic_task(base_sha, "tier_1", tasks)
    sample2 = select_deterministic_task(base_sha, "tier_1", tasks)
    assert sample1 == sample2

    # Verification of formula: SHA256(base_sha + "m12-pilot-v1" + tier) % count
    seed1 = f"{base_sha}m12-pilot-v1tier_1".encode("utf-8")
    expected_hash = hashlib.sha256(seed1).hexdigest()
    expected_idx = int(expected_hash, 16) % len(tasks)
    assert sample1 == tasks[expected_idx]

    # Different tier yields different selection
    sample_t3 = select_deterministic_task(base_sha, "tier_3", tasks)
    seed3 = f"{base_sha}m12-pilot-v1tier_3".encode("utf-8")
    expected_t3_hash = hashlib.sha256(seed3).hexdigest()
    assert sample_t3 == tasks[int(expected_t3_hash, 16) % len(tasks)]

    # Empty task list raises ValueError
    with pytest.raises(ValueError):
        select_deterministic_task(base_sha, "tier_empty", [])


def test_dynamic_tier_corpus_evaluation(tmp_path: Path) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    (tasks_dir / "t1.json").write_text("{}", encoding="utf-8")
    (tasks_dir / "t2.json").write_text("{}", encoding="utf-8")
    (tasks_dir / "t3.json").write_text("{}", encoding="utf-8")

    cfg_file = tmp_path / "test_config.json"
    cfg_data = {
        "tiers": {
            "tier_complete": ["t1.json", "t2.json"],
            "tier_incomplete": [
                "t1.json",
                "missing_1.json",
                "missing_2.json",
            ],
            "tier_2": "all",
        }
    }
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    base_sha = "97d3dd5f3d663aa76d241f33ae606fd1c7668e94"
    statuses = evaluate_tier_corpus(
        config_path=cfg_file,
        tasks_dir=tasks_dir,
        base_sha=base_sha,
        check_git_tracking=False,
    )

    status_map = {s["name"]: s for s in statuses}

    # Complete tier
    assert status_map["tier_complete"]["blocked"] is False
    assert status_map["tier_complete"]["available_tasks"] == 2
    assert status_map["tier_complete"]["missing_tasks"] == []
    assert status_map["tier_complete"]["sample_task"] in ["t1.json", "t2.json"]

    # Incomplete tier (dynamically blocked)
    assert status_map["tier_incomplete"]["blocked"] is True
    assert status_map["tier_incomplete"]["available_tasks"] == 1
    assert set(status_map["tier_incomplete"]["missing_tasks"]) == {
        "missing_1.json",
        "missing_2.json",
    }

    # Rollup tier
    assert status_map["tier_2"]["is_rollup"] is True
    assert status_map["tier_2"]["blocked"] is False
    assert status_map["tier_2"]["sample_task"] is None


def test_baseline_git_tracking_blocks_untracked_tasks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()

    # Both task files exist on disk
    (tasks_dir / "tracked.json").write_text("{}", encoding="utf-8")
    (tasks_dir / "untracked.json").write_text("{}", encoding="utf-8")

    cfg_file = tmp_path / "test_config.json"
    cfg_data = {
        "tiers": {
            "tier_mixed": ["tracked.json", "untracked.json"],
        }
    }
    cfg_file.write_text(json.dumps(cfg_data), encoding="utf-8")

    def mock_tracked(
        _sha: str, _dir: Path, _root: Path = Path(".")
    ) -> set[str]:
        return {"tracked.json"}

    monkeypatch.setattr(
        "eval.reliability_matrix.get_baseline_tracked_tasks",
        mock_tracked,
    )

    statuses = evaluate_tier_corpus(
        config_path=cfg_file,
        tasks_dir=tasks_dir,
        base_sha="97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
        check_git_tracking=True,
    )
    status = statuses[0]
    # Even though untracked.json is on disk, missing from git tree blocks tier
    assert status["blocked"] is True
    assert status["available_tasks"] == 1
    assert status["missing_tasks"] == ["untracked.json"]


def test_git_lookup_failure_fails_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tasks_dir = tmp_path / "tasks"
    tasks_dir.mkdir()
    (tasks_dir / "t1.json").write_text("{}", encoding="utf-8")

    cfg_file = tmp_path / "test_config.json"
    cfg_file.write_text(
        json.dumps({"tiers": {"tier_test": ["t1.json"]}}),
        encoding="utf-8",
    )

    def mock_tracked_error(
        _sha: str, _dir: Path, _root: Path = Path(".")
    ) -> set[str]:
        raise RuntimeError("simulated git ls-tree failure")

    monkeypatch.setattr(
        "eval.reliability_matrix.get_baseline_tracked_tasks",
        mock_tracked_error,
    )

    statuses = evaluate_tier_corpus(
        config_path=cfg_file,
        tasks_dir=tasks_dir,
        base_sha="97d3dd5f3d663aa76d241f33ae606fd1c7668e94",
        check_git_tracking=True,
    )
    assert statuses[0]["blocked"] is True
    assert statuses[0]["available_tasks"] == 0
    assert "git_provenance_error" in statuses[0]["missing_tasks"][0]


def test_live_baseline_corpus_tier_blocking() -> None:
    base_sha = "97d3dd5f3d663aa76d241f33ae606fd1c7668e94"
    statuses = evaluate_tier_corpus(
        config_path=DEFAULT_CONFIG_PATH,
        tasks_dir=Path("tasks/benchmark"),
        base_sha=base_sha,
        check_git_tracking=True,
    )
    status_map = {s["name"]: s for s in statuses}

    # Tiers 1-7 are tracked in git baseline
    for tier in [
        "tier_1", "tier_overnight", "tier_3",
        "tier_4", "tier_5", "tier_6", "tier_7",
    ]:
        assert status_map[tier]["blocked"] is False
        assert status_map[tier]["available_tasks"] > 0
        assert status_map[tier]["missing_tasks"] == []

    # Tier 2 is rollup
    assert status_map["tier_2"]["is_rollup"] is True

    # Tier 8 & 9 exist only as ignored local files, NOT in git baseline ->
    # BLOCKED
    assert status_map["tier_8"]["blocked"] is True
    assert status_map["tier_8"]["available_tasks"] == 0
    assert len(status_map["tier_8"]["missing_tasks"]) == 15
    assert "task_2000_distributed_lock_consensus.json" in (
        status_map["tier_8"]["missing_tasks"]
    )

    assert status_map["tier_9"]["blocked"] is True
    assert status_map["tier_9"]["available_tasks"] == 0
    assert len(status_map["tier_9"]["missing_tasks"]) == 5
    assert "task_3000_raft_consensus_state_machine.json" in (
        status_map["tier_9"]["missing_tasks"]
    )


def test_runner_lock_contention(tmp_path: Path) -> None:
    lock_file = tmp_path / "eval_runner.lock"

    # Acquire lock in first instance
    with SingleInstanceLock(lock_file):
        # Second attempt must be rejected
        with pytest.raises(SingleInstanceLockError):
            with SingleInstanceLock(lock_file):
                pass

    # After exit, acquiring lock succeeds again
    with SingleInstanceLock(lock_file):
        pass


def test_usage_instrumentation_thread_safety() -> None:
    instrumentation = UsageInstrumentation()

    class MockOllamaClient:
        def __init__(self) -> None:
            self.model_name = "gemma4:e4b"
            self.config = {"temperature": 0.2, "max_tokens": 4000}
            self.last_metadata = {
                "usage": {
                    "prompt_tokens": 100,
                    "completion_tokens": 50,
                    "total_tokens": 150,
                },
                "latency_seconds": 0.5,
            }

        def generate_content(self, sys_instr: str, user_prompt: str) -> str:
            return f"response to {user_prompt}"

    client = MockOllamaClient()
    instrumentation.wrap_ollama_client(client)

    threads = []
    calls_per_thread = 5

    def worker(tid: int) -> None:
        for i in range(calls_per_thread):
            res = client.generate_content("sys", f"query {tid}-{i}")
            assert "response to" in res

    for t_idx in range(4):
        t = threading.Thread(target=worker, args=(t_idx,))
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    assert instrumentation.generation_calls == 4 * calls_per_thread
    assert len(instrumentation.events) == 4 * calls_per_thread
    assert instrumentation.token_coverage_complete is True

    # Test missing metadata marks token_coverage_complete = False
    client.last_metadata = {}
    client.generate_content("sys", "query missing")
    assert instrumentation.token_coverage_complete is False


def test_arms_definition_invariants() -> None:
    assert len(ARMS) == 5
    expected_ids = {
        "control_once",
        "mm_single",
        "mm_swarm",
        "mm_single_recovery",
        "mm_swarm_recovery",
    }
    assert set(ARMS.keys()) == expected_ids

    # mm_swarm_recovery invariants
    swarm_rec = ARMS["mm_swarm_recovery"]
    assert swarm_rec.execution_mode == "swarm_solve"
    assert swarm_rec.recovery_enabled is True
    assert "concurrency=2" in swarm_rec.description
    assert "agent recovery" in swarm_rec.description

    assert SWARM_CONCURRENCY == 2
    assert MAX_RECOVERY_ATTEMPTS == 1


def test_dry_run_preflight_zero_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "results"
    lock_file = tmp_path / "test.lock"

    # Ensure no OllamaClient.generate_content call can happen
    mock_gen = MagicMock(
        side_effect=RuntimeError("Generation forbidden during dry-run")
    )
    monkeypatch.setattr(
        "eval.reliability_matrix.urllib.request.urlopen",
        MagicMock(),
    )

    digest_val = (
        "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"
    )

    def mock_check_provenance(host: str, model: str) -> dict[str, Any]:
        return {
            "host": host,
            "available": True,
            "version": "0.33.2",
            "model": model,
            "model_digest": digest_val,
        }

    monkeypatch.setattr(
        "eval.reliability_matrix.check_ollama_provenance",
        mock_check_provenance,
    )

    report = run_preflight(
        experiment_id="test-exp-zero-gen",
        output_dir=out_dir,
        lock_path=lock_file,
    )

    assert report["dry_run"] is True
    assert report["generation_calls"] == 0
    assert report["recovery_attempt_ceiling"] == 1
    assert mock_gen.call_count == 0

    # Report file saved and matches
    saved_file = out_dir / "preflight_report.json"
    assert saved_file.is_file()
    saved_report = json.loads(saved_file.read_text(encoding="utf-8"))
    assert saved_report["experiment_id"] == "test-exp-zero-gen"
    assert saved_report["generation_calls"] == 0


def test_blocked_tier_causes_overall_preflight_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "results"
    lock_file = tmp_path / "test.lock"

    digest_val = (
        "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"
    )

    monkeypatch.setattr(
        "eval.reliability_matrix.check_ollama_provenance",
        lambda host, model: {
            "host": host,
            "available": True,
            "version": "0.33.2",
            "model": model,
            "model_digest": digest_val,
        },
    )

    report = run_preflight(
        experiment_id="test-blocked",
        output_dir=out_dir,
        lock_path=lock_file,
        check_git_tracking=True,
    )
    # Tier 8 & 9 are blocked on current baseline -> preflight must fail
    assert report["preflight_passed"] is False
    assert any("tier_8" in r for r in report["blocking_reasons"])
    assert any("tier_9" in r for r in report["blocking_reasons"])


def test_ollama_unavailable_causes_overall_preflight_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "results"
    lock_file = tmp_path / "test.lock"

    monkeypatch.setattr(
        "eval.reliability_matrix.check_ollama_provenance",
        lambda host, model: {
            "host": host,
            "available": False,
            "version": "unknown",
            "model": model,
            "model_digest": "unknown",
            "error": "Connection refused",
        },
    )

    report = run_preflight(
        experiment_id="test-no-ollama",
        output_dir=out_dir,
        lock_path=lock_file,
    )
    assert report["preflight_passed"] is False
    assert any(
        "Ollama server unavailable" in r for r in report["blocking_reasons"]
    )


def test_dirty_worktree_causes_overall_preflight_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "results"
    lock_file = tmp_path / "test.lock"

    monkeypatch.setattr(
        "eval.reliability_matrix.check_git_clean",
        lambda _root=Path("."): (False, ["?? unapproved_file.py"]),
    )

    digest_val = (
        "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"
    )
    monkeypatch.setattr(
        "eval.reliability_matrix.check_ollama_provenance",
        lambda host, model: {
            "host": host,
            "available": True,
            "version": "0.33.2",
            "model": model,
            "model_digest": digest_val,
        },
    )

    report = run_preflight(
        experiment_id="test-dirty",
        output_dir=out_dir,
        lock_path=lock_file,
    )
    assert report["preflight_passed"] is False
    assert any(
        "unapproved dirty files" in r for r in report["blocking_reasons"]
    )


def test_clean_mocked_preflight_passes(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "results"
    lock_file = tmp_path / "test.lock"

    digest_val = (
        "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"
    )
    monkeypatch.setattr(
        "eval.reliability_matrix.check_ollama_provenance",
        lambda host, model: {
            "host": host,
            "available": True,
            "version": "0.33.2",
            "model": model,
            "model_digest": digest_val,
        },
    )
    monkeypatch.setattr(
        "eval.reliability_matrix.check_git_clean",
        lambda _root=Path("."): (True, []),
    )
    monkeypatch.setattr(
        "eval.reliability_matrix.evaluate_tier_corpus",
        lambda cfg, tdir, sha, check: [
            {
                "name": "tier_1",
                "is_rollup": False,
                "total_configured": 1,
                "available_tasks": 1,
                "missing_tasks": [],
                "blocked": False,
                "sample_task": "t1.json",
            }
        ],
    )

    monkeypatch.setattr(
        "eval.reliability_matrix.verify_runtime_context_readiness",
        lambda *a, **kw: (True, None),
    )
    report = run_preflight(
        experiment_id="test-clean-pass",
        output_dir=out_dir,
        lock_path=lock_file,
    )
    assert report["preflight_passed"] is True
    assert report["blocking_reasons"] == []

    # main() returns 0 when preflight_passed is True
    monkeypatch.setattr(
        "eval.reliability_matrix.run_preflight",
        lambda **kwargs: report,
    )
    exit_code = main(["--dry-run", "--output-dir", str(out_dir)])
    assert exit_code == 0


def test_dry_run_cli_main(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    out_dir = tmp_path / "cli_results"

    digest_val = (
        "c6eb396dbd5992bbe3f5cdb947e8bbc0ee413d7c17e2beaae69f5d569cf982eb"
    )

    def mock_check_provenance(host: str, model: str) -> dict[str, Any]:
        return {
            "host": host,
            "available": True,
            "version": "0.33.2",
            "model": model,
            "model_digest": digest_val,
        }

    monkeypatch.setattr(
        "eval.reliability_matrix.check_ollama_provenance",
        mock_check_provenance,
    )

    # Against live baseline, Tier 8/9 blocked -> exit code 1
    exit_code = main([
        "--dry-run",
        "--experiment-id", "cli-test",
        "--output-dir", str(out_dir),
    ])
    assert exit_code == 1
    assert (out_dir / "preflight_report.json").is_file()
    saved = json.loads(
        (out_dir / "preflight_report.json").read_text(encoding="utf-8")
    )
    assert saved["preflight_passed"] is False
    assert saved["generation_calls"] == 0
