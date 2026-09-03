"""Tests for eval/reliability_matrix_execution.py and five-arm engine."""

from __future__ import annotations

import copy
import hashlib
import json
import jsonschema
import os
from pathlib import Path
import threading
from unittest.mock import MagicMock, patch

import pytest

from eval.reliability_matrix import (
    DEFAULT_TASKS_DIR,
    EXPERIMENT_BASE_SHA,
    SCHEMA_VERSION,
    SWARM_CONCURRENCY,
    compute_sha256_bytes,
    resolve_harness_sha,
    run_preflight,
    select_deterministic_p2_tasks,
    validate_payload_against_schema,
    verify_baseline_harness_delta,
)
import eval.run_bare_baseline as bare_baseline
from eval.reliability_matrix_execution import (
    ARM_ORDER_SEED_PREFIX,
    ARMS,
    BARE_PROMPT_TEMPLATE,
    CaptureOllamaUsage,
    P1_TIERS,
    P2_ARMS,
    P2_PLAN_DESIGN,
    P2_TIERS,
    classify_failure,
    deterministic_arm_order,
    execute_matrix_plan,
    execute_trial_unit,
    materialize_p1_plan,
    materialize_p2_plan,
    prepare_fresh_trial_workspace,
    validate_execution_plan,
)
from mighty_mouse.host.adapter import HostAdapter
from mighty_mouse.host.hooks import (
    HostHookAction,
    HostHookEvent,
    HookVerificationSummary,
    ResolvedHostHookEvent,
)
from mighty_mouse.host.recovery import evaluate_recovery_gate
from mighty_mouse.orchestrator.ollama_client import OllamaClient


def test_deterministic_arm_ordering_invariants() -> None:
    """Verify exact arm ordering match against specification for P1 tasks."""
    base_sha = EXPERIMENT_BASE_SHA
    order_003 = deterministic_arm_order(base_sha, "task_003", 1)
    assert order_003 == [
        "mm_swarm",
        "control_once",
        "mm_swarm_recovery",
        "mm_single",
        "mm_single_recovery",
    ]

    order_047 = deterministic_arm_order(base_sha, "task_047", 1)
    assert order_047 == [
        "control_once",
        "mm_swarm",
        "mm_swarm_recovery",
        "mm_single",
        "mm_single_recovery",
    ]

    order_1415 = deterministic_arm_order(base_sha, "task_1415", 1)
    assert order_1415 == [
        "mm_single",
        "mm_swarm",
        "mm_single_recovery",
        "control_once",
        "mm_swarm_recovery",
    ]


def test_materialize_p1_plan_zero_generation(tmp_path: Path) -> None:
    """Verify zero-generation P1 plan materialization and schema validity."""
    out_dir = tmp_path / "plan_out"
    plan = materialize_p1_plan(
        experiment_id="test-p1-materialize",
        base_sha=EXPERIMENT_BASE_SHA,
        output_dir=out_dir,
    )
    assert plan["schema_version"] == SCHEMA_VERSION
    assert plan["experiment_id"] == "test-p1-materialize"
    assert plan["base_sha"] == EXPERIMENT_BASE_SHA
    assert plan["replicates"] == 1
    assert plan["tiers"] == ["tier_1", "tier_5", "tier_7"]
    assert plan["arm_order_seed"] == ARM_ORDER_SEED_PREFIX

    units = plan["trial_units"]
    assert len(units) == 15

    # Task 003 units (order 0-4)
    t003_arms = [u["arm"] for u in units[0:5]]
    assert t003_arms == [
        "mm_swarm",
        "control_once",
        "mm_swarm_recovery",
        "mm_single",
        "mm_single_recovery",
    ]
    for u in units[0:5]:
        assert u["task_id"] == "task_003"
        assert u["tier"] == "tier_1"
        assert u["replicate"] == 1

    # Task 047 units (order 5-9)
    t047_arms = [u["arm"] for u in units[5:10]]
    assert t047_arms == [
        "control_once",
        "mm_swarm",
        "mm_swarm_recovery",
        "mm_single",
        "mm_single_recovery",
    ]
    for u in units[5:10]:
        assert u["task_id"] == "task_047"
        assert u["tier"] == "tier_5"

    # Task 1415 units (order 10-14)
    t1415_arms = [u["arm"] for u in units[10:15]]
    assert t1415_arms == [
        "mm_single",
        "mm_swarm",
        "mm_single_recovery",
        "control_once",
        "mm_swarm_recovery",
    ]
    for u in units[10:15]:
        assert u["task_id"] == "task_1415"
        assert u["tier"] == "tier_7"

    # Order indexes are contiguous
    assert [u["order_index"] for u in units] == list(range(15))

    # Saved file matches
    saved_file = out_dir / "execution_plan.json"
    assert saved_file.is_file()
    saved_plan = json.loads(saved_file.read_text(encoding="utf-8"))
    assert saved_plan["trial_units"] == units


def test_provenance_separation_delta_checks(tmp_path: Path) -> None:
    """Verify delta between base and harness enforces closed M12 allowlist."""
    # Identical SHAs pass immediately
    ok, empty = verify_baseline_harness_delta("abc", "abc")
    assert ok is True
    assert empty == []

    # Mock git diff returning approved M12 harness surfaces
    approved_diff = (
        "eval/reliability_matrix.py\n"
        "eval/reliability_matrix_execution.py\n"
        "eval/reliability_matrix_contract.json\n"
        "eval/test_reliability_matrix.py\n"
        "eval/test_reliability_matrix_execution.py\n"
        "eval/test_non_agent_response_application_inventory.py\n"
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=approved_diff)
        ok, changed = verify_baseline_harness_delta("sha1", "sha2")
        assert ok is True
        assert len(changed) == 6

    # Unrelated eval/ changes fail closed
    unrelated_eval = (
        "eval/reliability_matrix.py\n"
        "eval/run_bare_baseline.py\n"
    )
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout=unrelated_eval)
        ok, unapproved = verify_baseline_harness_delta("sha1", "sha2")
        assert ok is False
        assert unapproved == ["eval/run_bare_baseline.py"]

    # Production / non-eval changes fail closed
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=(
                "eval/reliability_matrix.py\n"
                "src/mighty_mouse/host/adapter.py\n"
            ),
        )
        ok, unapproved = verify_baseline_harness_delta("sha1", "sha2")
        assert ok is False
        assert unapproved == ["src/mighty_mouse/host/adapter.py"]


def test_scoped_preflight_passes_without_tier_8_9(tmp_path: Path) -> None:
    """Scoped P1 preflight requires only tiers 1, 5, 7, ignores tier 8/9."""
    out_dir = tmp_path / "scoped_preflight"
    lock_file = tmp_path / "test.lock"

    digest_val = "sha256:" + "a" * 64
    with patch(
        "eval.reliability_matrix.check_ollama_provenance",
        return_value={
            "host": "http://localhost:11434",
            "available": True,
            "version": "0.33.2",
            "model": "gemma4:e4b",
            "model_digest": digest_val,
        },
    ), patch(
        "eval.reliability_matrix.check_git_clean",
        return_value=(True, []),
    ), patch(
        "eval.reliability_matrix.verify_baseline_harness_delta",
        return_value=(True, []),
    ), patch(
        "eval.reliability_matrix.verify_runtime_context_readiness",
        return_value=(True, None),
    ):
        report = run_preflight(
            experiment_id="test-scoped-pass",
            base_sha=EXPERIMENT_BASE_SHA,
            output_dir=out_dir,
            lock_path=lock_file,
            required_tiers=["tier_1", "tier_5", "tier_7"],
        )
        assert report["preflight_passed"] is True
        assert report["blocking_reasons"] == []
        assert report["required_tiers"] == ["tier_1", "tier_5", "tier_7"]


def test_capture_ollama_usage_context_manager() -> None:
    """CaptureOllamaUsage intercepts generate_content at class level."""
    orig_generate = OllamaClient.generate_content
    capture = CaptureOllamaUsage()

    client1 = OllamaClient(
        {"ollama_host": "http://mock", "model": "gemma4:e4b"}
    )
    client2 = OllamaClient(
        {"ollama_host": "http://mock", "model": "gemma4:e4b"}
    )

    def fake_gen(self, sys_instr, user_prompt):
        self.last_metadata = {
            "usage": {
                "prompt_tokens": 100,
                "completion_tokens": 20,
                "total_tokens": 120,
            },
            "latency_seconds": 0.5,
        }
        return "response"

    with patch.object(OllamaClient, "generate_content", fake_gen):
        with capture:
            assert OllamaClient.generate_content != fake_gen

            capture.set_phase("primary")
            client1.generate_content("sys1", "user1")

            capture.set_phase("recovery")
            client2.generate_content("sys2", "user2")

        assert OllamaClient.generate_content == fake_gen

    assert OllamaClient.generate_content == orig_generate

    assert capture.generation_calls == 2
    assert len(capture.events) == 2
    assert capture.events[0]["phase"] == "primary"
    assert capture.events[0]["prompt_tokens"] == 100
    assert capture.events[1]["phase"] == "recovery"
    assert capture.events[1]["completion_tokens"] == 20
    assert capture.token_coverage_complete is True


def test_capture_ollama_usage_missing_tokens_marks_incomplete() -> None:
    """Missing prompt/completion tokens sets token_coverage_complete False."""
    capture = CaptureOllamaUsage()

    def fake_gen_missing(self, sys_instr, user_prompt):
        self.last_metadata = {
            "usage": {"prompt_tokens": None, "completion_tokens": 10},
            "latency_seconds": 0.1,
        }
        return "res"

    with patch.object(OllamaClient, "generate_content", fake_gen_missing):
        with capture:
            client = OllamaClient({})
            client.generate_content("", "")

    assert capture.token_coverage_complete is False


def test_capture_ollama_usage_thread_safety() -> None:
    """Concurrent threads safely record calls without race conditions."""
    capture = CaptureOllamaUsage()
    client = OllamaClient({})

    def fake_threaded(self, sys_instr, user_prompt):
        self.last_metadata = {
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 5,
                "total_tokens": 10,
            },
            "latency_seconds": 0.05,
        }
        return "ok"

    with patch.object(OllamaClient, "generate_content", fake_threaded):
        with capture:
            def worker():
                for _ in range(25):
                    client.generate_content("", "")

            threads = [threading.Thread(target=worker) for _ in range(4)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

    assert capture.generation_calls == 100
    assert len(capture.events) == 100
    assert capture.token_coverage_complete is True


def test_recovery_post_action_envelope_synthesis(tmp_path: Path) -> None:
    """Synthesize post_action envelope and evaluate gate eligibility."""
    ws = tmp_path / "recovery_env_ws"
    ws.mkdir()
    state_dir = ws / ".mighty-mouse"
    state_dir.mkdir()

    from mighty_mouse.host.adapter import (
        HostAdapter,
        MCP_TOOL_CONTRACT_VERSION,
    )
    cfg = HostAdapter.build_adapter_config(
        repository="JOHNNYMACONNY/mighty-mouse",
        model_digest="sha256:" + "b" * 64,
        model_class="local-small",
        effective_context_limit=8192,
        runtime_kind="cline",
        runtime_version="3.54.0",
        ollama_model=None,
        tool_signatures={"verify": lambda w: None},
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    (state_dir / "mcp-adapter.json").write_text(
        json.dumps(cfg), encoding="utf-8"
    )

    action = HostHookAction(
        kind="file_write",
        mutation_class="workspace_mutation",
        target_paths=("legacy_link.py",),
    )
    event = HostHookEvent(
        schema_version=1,
        event_id="m12-rec-test-01",
        phase="post_action",
        workspace=str(ws),
        action=action,
        source="m12_reliability_matrix",
    )
    ctx = HostAdapter().resolve_adapter_context(
        workspace=str(ws),
        tool_signatures={"verify": lambda w: None},
    )
    resolved = ResolvedHostHookEvent(event=event, runtime_context=ctx)
    verif = HookVerificationSummary(
        occurred=True,
        passed=False,
        summary="Unit test failed: circuitbreaker open timeout",
    )

    decision = evaluate_recovery_gate(
        resolved,
        verif,
        enabled=True,
        attempts_used=0,
        recovery_in_progress=False,
    )
    assert decision.eligible is True
    assert decision.gate_reason == "eligible"
    assert decision.execution_mode == "agent"


@pytest.fixture
def mock_trial_environment(tmp_path: Path):
    """Setup mock environment for zero-live-generation unit trials."""
    ws_root = tmp_path / "workspaces"
    out_dir = tmp_path / "results"
    tasks_dir = tmp_path / "tasks"
    ws_root.mkdir()
    out_dir.mkdir()
    tasks_dir.mkdir()

    task_003 = {
        "id": "task_003",
        "title": "Legacy Link Circuitbreaker",
        "description": "Fix retry circuitbreaker",
        "expected_files": ["legacy_link.py"],
        "test_script": "assert True",
    }
    (tasks_dir / "task_003_legacy_link_circuitbreaker.json").write_text(
        json.dumps(task_003), encoding="utf-8"
    )

    canonical_digest = (
        "sha256:4c27e0f5b5adf02a"
        "c956c7322bd2ee7636fe3f45a8512c9aba5385242cb6e09a"
    )
    adapter_dir = Path(".mighty-mouse")
    adapter_path = adapter_dir / "mcp-adapter.json"
    created_adapter = False

    with patch.object(
        HostAdapter,
        "resolve_ollama_model_digest",
        return_value=canonical_digest,
    ):
        if not adapter_path.is_file():
            adapter_dir.mkdir(parents=True, exist_ok=True)
            from mighty_mouse_mcp.server import _get_mcp_tool_signatures

            cfg = HostAdapter.build_adapter_config(
                repository="JOHNNYMACONNY/mighty-mouse",
                model_digest=canonical_digest,
                model_class="local-small",
                effective_context_limit=8192,
                runtime_kind="antigravity",
                runtime_version="1.0.0",
                ollama_model="gemma4:e4b",
                tool_signatures=_get_mcp_tool_signatures(),
            )
            adapter_path.write_text(json.dumps(cfg), encoding="utf-8")
            created_adapter = True
        else:
            cfg = json.loads(adapter_path.read_text(encoding="utf-8"))

        test_digest = cfg.get("model_digest", canonical_digest)

        prov_info = {
            "host": "http://localhost:11434",
            "available": True,
            "version": "0.33.2",
            "model": "gemma4:e4b",
            "model_digest": test_digest,
        }

        try:
            yield ws_root, out_dir, tasks_dir, prov_info
        finally:
            if created_adapter and adapter_path.is_file():
                adapter_path.unlink()


def test_execute_trial_arm_control_once(mock_trial_environment) -> None:
    """Qualify arm 1 (control_once) with mocked bare generation."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_id": "trial_t1_003_control_once_rep1",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
    }

    mock_resp = "```python:legacy_link.py\nprint('fixed')\n```"
    mock_meta = {
        "prompt_tokens": 120,
        "completion_tokens": 30,
        "latency_seconds": 0.45,
    }

    pass_verif = {
        "status": "success",
        "scope": "PASS",
        "adherence": "PASS",
    }

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=pass_verif,
    ):
        record = execute_trial_unit(
            plan_unit,
            experiment_id="test-arm-1",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(record, "trial_record")
    assert record["identity"]["arm"] == "control_once"
    assert record["verification"]["first_passed"] is True
    assert record["verification"]["terminal_passed"] is True
    assert record["execution"]["recovery_attempted"] is False
    assert record["cost"]["primary_prompt_tokens"] == 120
    assert record["cost"]["primary_completion_tokens"] == 30
    assert record["cost"]["recovery_prompt_tokens"] == 0
    assert record["validity"]["token_coverage_complete"] is True


def test_execute_trial_arm_mm_single(mock_trial_environment) -> None:
    """Qualify arm 2 (mm_single) calling HostAdapter.solve."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 1,
        "trial_id": "trial_t1_003_mm_single_rep1",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_single",
        "replicate": 1,
    }

    def fake_solve(*args, **kwargs):
        pass

    capture = CaptureOllamaUsage()
    capture.record_generation(
        phase="primary",
        prompt_tokens=250,
        completion_tokens=60,
        latency_seconds=0.8,
    )

    pass_verif = {
        "status": "success",
        "scope": "PASS",
        "adherence": "PASS",
    }

    with patch.object(
        HostAdapter, "solve", side_effect=fake_solve
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=pass_verif,
    ):
        record = execute_trial_unit(
            plan_unit,
            experiment_id="test-arm-2",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
            usage_capture=capture,
        )

    validate_payload_against_schema(record, "trial_record")
    assert record["identity"]["arm"] == "mm_single"
    assert record["verification"]["terminal_passed"] is True
    assert record["execution"]["recovery_enabled"] is False
    assert record["execution"]["recovery_attempted"] is False


def test_execute_trial_arm_mm_swarm(mock_trial_environment) -> None:
    """Qualify arm 3 (mm_swarm) calling solve_swarm with concurrency=2."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 2,
        "trial_id": "trial_t1_003_mm_swarm_rep1",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_swarm",
        "replicate": 1,
    }

    swarm_called = False

    def fake_solve_swarm(self, *args, **kwargs):
        nonlocal swarm_called
        swarm_called = True
        assert kwargs.get("concurrency") == SWARM_CONCURRENCY
        assert "verification_workspace" in kwargs
        return {"pipeline_result": {"status": "success"}}

    capture = CaptureOllamaUsage()
    capture.record_generation(
        phase="primary",
        prompt_tokens=400,
        completion_tokens=100,
        latency_seconds=1.2,
    )

    pass_verif = {
        "status": "success",
        "scope": "PASS",
        "adherence": "PASS",
    }

    with patch.object(
        HostAdapter, "solve_swarm", fake_solve_swarm
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=pass_verif,
    ):
        record = execute_trial_unit(
            plan_unit,
            experiment_id="test-arm-3",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
            usage_capture=capture,
        )

    validate_payload_against_schema(record, "trial_record")
    assert swarm_called is True
    assert record["identity"]["arm"] == "mm_swarm"
    assert record["execution"]["swarm_concurrency"] == 2
    assert record["execution"]["recovery_attempted"] is False


def test_execute_trial_arm_mm_single_recovery_success(
    mock_trial_environment,
) -> None:
    """Qualify arm 4: primary fails, recovery attempt passes reverence."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 3,
        "trial_id": "trial_t1_003_mm_single_recovery_rep1",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_single_recovery",
        "replicate": 1,
    }

    verif_calls = 0

    def fake_verify(task_config, workspace=None):
        nonlocal verif_calls
        verif_calls += 1
        if verif_calls == 1:
            return {
                "status": "fail",
                "scope": "PASS",
                "adherence": "PASS",
                "reason": "AssertionError: 5 != 10",
            }
        return {
            "status": "success",
            "scope": "PASS",
            "adherence": "PASS",
            "reason": "All checks passed",
        }

    from mighty_mouse.host.recovery_execution import RecoveryExecutionAttempt

    def fake_recovery(request, feedback_str=None):
        return RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=1,
            execution_mode="agent",
            output_paths=("legacy_link.py",),
        )

    capture = CaptureOllamaUsage()
    capture.record_generation(
        phase="primary", prompt_tokens=200, completion_tokens=50
    )
    capture.record_generation(
        phase="recovery", prompt_tokens=150, completion_tokens=40
    )

    with patch.object(
        HostAdapter, "solve", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        side_effect=fake_verify,
    ), patch(
        "eval.reliability_matrix_execution.execute_recovery_attempt",
        side_effect=fake_recovery,
    ):
        record = execute_trial_unit(
            plan_unit,
            experiment_id="test-arm-4",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
            usage_capture=capture,
        )

    validate_payload_against_schema(record, "trial_record")
    assert record["identity"]["arm"] == "mm_single_recovery"
    assert record["verification"]["first_passed"] is False
    assert record["verification"]["first_failure_category"] == "test_failure"
    assert record["verification"]["recovery_eligible"] is True
    assert record["verification"]["recovery_gate_reason"] == "eligible"
    assert record["execution"]["recovery_attempted"] is True
    assert record["execution"]["recovery_completed"] is True
    assert record["verification"]["terminal_passed"] is True
    assert record["verification"]["terminal_failure_category"] is None
    assert record["cost"]["primary_prompt_tokens"] == 200
    assert record["cost"]["recovery_prompt_tokens"] == 150
    assert record["cost"]["total_tokens"] == 440


def test_execute_trial_arm_mm_swarm_recovery_agent_only(
    mock_trial_environment,
) -> None:
    """Qualify arm 5: swarm primary fails -> strictly agent-only recovery."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 4,
        "trial_id": "trial_t1_003_mm_swarm_recovery_rep1",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_swarm_recovery",
        "replicate": 1,
    }

    recovery_invoked_mode = None
    from mighty_mouse.host.recovery_execution import RecoveryExecutionAttempt

    def fake_recovery(request, feedback_str=None):
        nonlocal recovery_invoked_mode
        recovery_invoked_mode = request.decision.execution_mode
        assert request.decision.execution_mode == "agent"  # Never swarm
        return RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=1,
            execution_mode="agent",
            output_paths=("legacy_link.py",),
        )

    verif_count = 0

    def fake_verify(task_config, workspace=None):
        nonlocal verif_count
        verif_count += 1
        if verif_count == 1:
            return {"status": "fail", "reason": "SyntaxError"}
        return {"status": "fail", "reason": "Still broken"}

    with patch.object(
        HostAdapter, "solve_swarm", return_value={}
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        side_effect=fake_verify,
    ), patch(
        "eval.reliability_matrix_execution.execute_recovery_attempt",
        side_effect=fake_recovery,
    ):
        record = execute_trial_unit(
            plan_unit,
            experiment_id="test-arm-5",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(record, "trial_record")
    assert recovery_invoked_mode == "agent"
    assert record["identity"]["arm"] == "mm_swarm_recovery"
    assert record["execution"]["recovery_attempted"] is True
    assert record["verification"]["terminal_passed"] is False
    assert (
        record["verification"]["terminal_failure_category"]
        == "recovery_failed"
    )


def test_classify_failure_categories() -> None:
    """Verify correct failure classification across all enum states."""
    assert classify_failure({"status": "success"}) is None
    assert classify_failure(
        {"status": "fail", "scope": "FAIL", "adherence": "PASS"}
    ) == "scope_failure"
    assert classify_failure(
        {"status": "fail", "scope": "PASS", "adherence": "FAIL"}
    ) == "adherence_failure"
    assert classify_failure(
        {"status": "fail", "scope": "PASS", "adherence": "PASS"}
    ) == "test_failure"
    assert classify_failure(
        {"status": "fail"}, is_recovery=True
    ) == "recovery_failed"
    assert classify_failure(None) == "verifier_error"
    assert classify_failure(None, exception=TimeoutError()) == "timeout"
    assert classify_failure(
        None, exception=RuntimeError("ollama connection failed")
    ) == "generation_error"


def test_execute_matrix_plan_and_run_summary(mock_trial_environment) -> None:
    """Execute complete mini plan and verify run_summary.json schema."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan = materialize_p1_plan(tiers=["tier_1"])

    mock_resp = "```python:legacy_link.py\npass\n```"
    mock_meta = {
        "prompt_tokens": 50,
        "completion_tokens": 10,
        "total_tokens": 60,
        "latency_seconds": 0.2,
    }

    pass_verif = {
        "status": "success",
        "scope": "PASS",
        "adherence": "PASS",
    }

    preflight_mock = {
        "preflight_passed": True,
        "blocking_reasons": [],
        "ollama_server": {
            "host": "http://localhost:11434",
            "available": True,
            "version": "0.33.2",
            "model": "gemma4:e4b",
            "model_digest": prov_info["model_digest"],
        },
    }

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ), patch.object(
        HostAdapter, "solve", return_value=None
    ), patch.object(
        HostAdapter, "solve_swarm", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=pass_verif,
    ), patch(
        "eval.reliability_matrix_execution.check_ollama_provenance",
        return_value=prov_info,
    ), patch(
        "eval.reliability_matrix.run_preflight",
        return_value=preflight_mock,
    ):
        summary = execute_matrix_plan(
            plan,
            workspace_root=ws_root,
            output_dir=out_dir,
            tasks_dir=tasks_dir,
            lock_path=ws_root / "lock.file",
        )

    validate_payload_against_schema(summary, "run_summary")
    assert summary["status"] == "completed"
    assert summary["stop_reason"] is None
    assert summary["trial_count"] == 5
    assert summary["metrics"]["total_passed"] == 5
    assert summary["metrics"]["total_analyzable"] == 5
    assert summary["metrics"]["total_infrastructure_excluded"] == 0
    assert (out_dir / "run_summary.json").is_file()


def test_raw_control_missing_tokens_integrity() -> None:
    """Raw control with absent token fields sets coverage incomplete."""
    from eval.reliability_matrix_execution import request_control_generation

    mock_body = json.dumps({"response": "pass"}).encode("utf-8")
    mock_resp = MagicMock()
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_resp):
        response, meta = request_control_generation(
            "prompt", "gemma4:e4b", "http://localhost:11434", 10
        )
    assert response == "pass"
    assert meta["prompt_tokens"] is None
    assert meta["completion_tokens"] is None
    assert meta["total_tokens"] is None

    capture = CaptureOllamaUsage()
    capture.record_generation(
        phase="primary",
        model="gemma4:e4b",
        prompt_tokens=meta["prompt_tokens"],
        completion_tokens=meta["completion_tokens"],
        total_tokens=meta["total_tokens"],
    )
    assert capture.token_coverage_complete is False


def test_usage_capture_exception_resilience() -> None:
    """Original generate_content is restored even when exception thrown."""
    orig_generate = OllamaClient.generate_content
    capture = CaptureOllamaUsage()

    with pytest.raises(RuntimeError):
        with capture:
            assert OllamaClient.generate_content != orig_generate
            raise RuntimeError("Boom inside capture context")

    assert OllamaClient.generate_content == orig_generate


def test_usage_capture_records_thread_name() -> None:
    """Usage capture records current thread ID and thread name."""
    capture = CaptureOllamaUsage()
    capture.record_generation(
        phase="primary",
        prompt_tokens=10,
        completion_tokens=10,
    )
    assert len(capture.events) == 1
    assert capture.events[0]["thread_name"] == threading.current_thread().name
    assert capture.events[0]["thread_id"] == threading.get_ident()


def test_plan_materialization_uses_experiment_base_sha_always() -> None:
    """Plan selection uses experiment_base_sha even if harness_sha changes."""
    plan = materialize_p1_plan(
        base_sha=EXPERIMENT_BASE_SHA,
        harness_sha="1" * 40,
    )
    assert plan["experiment_base_sha"] == EXPERIMENT_BASE_SHA
    assert plan["base_sha"] == EXPERIMENT_BASE_SHA
    assert plan["harness_sha"] == "1" * 40
    for u in plan["trial_units"]:
        assert u["experiment_base_sha"] == EXPERIMENT_BASE_SHA
        assert u["harness_sha"] == "1" * 40
    tasks = [u["task_id"] for u in plan["trial_units"]]
    assert tasks[0:5] == ["task_003"] * 5
    assert tasks[5:10] == ["task_047"] * 5
    assert tasks[10:15] == ["task_1415"] * 5


def test_real_adapter_context_readiness_zero_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real adapter-context resolution succeeds with zero generation calls."""
    from eval.reliability_matrix import verify_runtime_context_readiness

    canonical_digest = (
        "sha256:4c27e0f5b5adf02a"
        "c956c7322bd2ee7636fe3f45a8512c9aba5385242cb6e09a"
    )
    monkeypatch.setattr(
        HostAdapter,
        "resolve_ollama_model_digest",
        lambda m: canonical_digest,
    )
    adapter_dir = Path(".mighty-mouse")
    adapter_path = adapter_dir / "mcp-adapter.json"
    created_adapter = False
    if not adapter_path.is_file():
        adapter_dir.mkdir(parents=True, exist_ok=True)
        from mighty_mouse_mcp.server import _get_mcp_tool_signatures

        cfg = HostAdapter.build_adapter_config(
            repository="JOHNNYMACONNY/mighty-mouse",
            model_digest=canonical_digest,
            model_class="local-small",
            effective_context_limit=8192,
            runtime_kind="antigravity",
            runtime_version="1.0.0",
            ollama_model="gemma4:e4b",
            tool_signatures=_get_mcp_tool_signatures(),
        )
        adapter_path.write_text(json.dumps(cfg), encoding="utf-8")
        created_adapter = True
    else:
        cfg = json.loads(adapter_path.read_text(encoding="utf-8"))

    digest = cfg.get("model_digest", canonical_digest)

    try:
        ok, err = verify_runtime_context_readiness(
            model_digest=digest,
            model="gemma4:e4b",
        )
        assert ok is True
        assert err is None
    finally:
        if created_adapter and adapter_path.is_file():
            adapter_path.unlink()


def test_trace_artifact_written_and_hashed(mock_trial_environment) -> None:
    """Trial execution writes trace artifact and records relpath + SHA256."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_trace_test",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": EXPERIMENT_BASE_SHA,
    }

    mock_resp = "```python:legacy_link.py\npass\n```"
    mock_meta = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_seconds": 0.1,
    }
    pass_verif = {
        "status": "success",
        "scope": "PASS",
        "adherence": "PASS",
    }

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=pass_verif,
    ):
        record = execute_trial_unit(
            plan_unit,
            experiment_id="test-trace-run",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    trace_file = out_dir / "traces" / "trial_trace_test.json"
    assert trace_file.is_file()
    trace_content = trace_file.read_bytes()
    expected_sha = hashlib.sha256(trace_content).hexdigest()

    assert (
        record["validity"]["trace_artifact_relpath"]
        == "traces/trial_trace_test.json"
    )
    assert record["validity"]["trace_artifact_sha256"] == expected_sha


def test_preexisting_trial_workspace_blocks_execution_and_preserves_evidence(
    mock_trial_environment,
) -> None:
    """Pre-existing workspace raises FileExistsError and preserves evidence."""
    from eval.reliability_matrix_execution import prepare_fresh_trial_workspace

    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    trial_id = "trial_preserve_evidence_test"
    target_ws = ws_root / trial_id
    target_ws.mkdir(parents=True, exist_ok=True)
    evidence_file = target_ws / "evidence_output.py"
    evidence_file.write_text(
        "# precious experimental evidence", encoding="utf-8"
    )

    # 1. prepare_fresh_trial_workspace fails closed
    with pytest.raises(FileExistsError, match="Fail closed to preserve"):
        prepare_fresh_trial_workspace(target_ws)
    assert evidence_file.is_file()
    assert (
        evidence_file.read_text(encoding="utf-8")
        == "# precious experimental evidence"
    )

    # 2. execute_trial_unit aborts before generation and leaves file intact
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": trial_id,
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    def poison_generator(*args, **kwargs):
        raise AssertionError("Model must not be called when workspace exists!")

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        side_effect=poison_generator,
    ):
        with pytest.raises(FileExistsError, match="Fail closed to preserve"):
            execute_trial_unit(
                plan_unit,
                experiment_id="test-preserve-evidence",
                workspace_root=ws_root,
                tasks_dir=tasks_dir,
                output_dir=out_dir,
                provenance_info=prov_info,
            )

    # Evidence is STILL intact
    assert evidence_file.is_file()
    assert (
        evidence_file.read_text(encoding="utf-8")
        == "# precious experimental evidence"
    )


def test_canonical_adapter_provenance_and_truthful_control(
    mock_trial_environment,
) -> None:
    """Control has null agent fields; MM arms have real values."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    harness_sha = resolve_harness_sha()

    # 1. Test control_once truthful provenance
    plan_unit_control = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_ctrl_prov",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": harness_sha,
    }

    mock_resp = "```python:legacy_link.py\npass\n```"
    mock_meta = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_seconds": 0.1,
    }
    pass_verif = {"status": "success", "scope": "PASS", "adherence": "PASS"}

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=pass_verif,
    ):
        ctrl_rec = execute_trial_unit(
            plan_unit_control,
            experiment_id="test-prov-run",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(ctrl_rec, "trial_record")
    ctrl_prov = ctrl_rec["provenance"]
    assert ctrl_prov["execution_profile_id"] is None
    assert ctrl_prov["tool_contract_digest"] is None
    assert ctrl_prov["runtime_version"] is None
    assert ctrl_prov["runtime_kind"] is None
    assert ctrl_prov["agent_config_sha256"] is None

    # 2. Test MM arm real provenance
    plan_unit_mm = {
        "order_index": 1,
        "trial_order_index": 1,
        "trial_id": "trial_mm_prov",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_single",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": harness_sha,
    }

    with patch.object(
        HostAdapter, "solve", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=pass_verif,
    ):
        mm_rec = execute_trial_unit(
            plan_unit_mm,
            experiment_id="test-prov-run",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(mm_rec, "trial_record")
    mm_prov = mm_rec["provenance"]
    assert mm_prov["execution_profile_id"] is not None
    assert mm_prov["tool_contract_digest"] is not None
    assert mm_prov["runtime_kind"] == "antigravity"
    assert mm_prov["runtime_version"] == "1.0.0"
    assert mm_prov["agent_config_sha256"] is not None


def test_fail_closed_on_unapproved_harness_delta(
    mock_trial_environment,
) -> None:
    """Execution halts before trial if unapproved delta detected."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_delta_fail",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    with patch(
        "eval.reliability_matrix_execution.verify_baseline_harness_delta",
        return_value=(False, ["eval/unapproved_file.py"]),
    ):
        with pytest.raises(
            RuntimeError,
            match="Baseline-to-harness delta check failed closed",
        ):
            execute_trial_unit(
                plan_unit,
                experiment_id="test-delta-fail",
                workspace_root=ws_root,
                tasks_dir=tasks_dir,
                output_dir=out_dir,
                provenance_info=prov_info,
            )


def test_true_zero_generation_dry_run(mock_trial_environment) -> None:
    """dry_run=True guarantees zero execution and zero generation calls."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan = materialize_p1_plan(tiers=["tier_1"])

    def poison_generation(*args, **kwargs):
        raise AssertionError("Generation was invoked during dry_run=True!")

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        side_effect=poison_generation,
    ), patch.object(
        OllamaClient, "generate_content", side_effect=poison_generation
    ), patch(
        "eval.reliability_matrix.run_preflight",
        return_value={"preflight_passed": True, "blocking_reasons": []},
    ):
        summary = execute_matrix_plan(
            plan,
            workspace_root=ws_root,
            output_dir=out_dir,
            tasks_dir=tasks_dir,
            lock_path=ws_root / "lock.file",
            dry_run=True,
        )

    validate_payload_against_schema(summary, "run_summary")
    assert summary["dry_run"] is True
    assert summary["status"] == "dry_run"
    assert summary["trial_count"] == 0
    assert summary["metrics"]["total_passed"] == 0
    assert summary["metrics"]["total_tokens"] is None


def test_scoped_preflight_gate_stops_execution(
    mock_trial_environment,
) -> None:
    """execute_matrix_plan aborts before trials if preflight fails."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan = materialize_p1_plan(tiers=["tier_1"])

    with patch(
        "eval.reliability_matrix.run_preflight",
        return_value={
            "preflight_passed": False,
            "blocking_reasons": ["Worktree dirty", "Ollama unreachable"],
        },
    ):
        with pytest.raises(
            RuntimeError,
            match="Scoped preflight failed before execution",
        ):
            execute_matrix_plan(
                plan,
                workspace_root=ws_root,
                output_dir=out_dir,
                tasks_dir=tasks_dir,
                lock_path=ws_root / "lock.file",
            )


def test_failed_generation_attempt_accounting(
    mock_trial_environment,
) -> None:
    """A model request that raises is still recorded as attempt."""
    capture = CaptureOllamaUsage()
    with capture:
        def mock_gen_fail(self, sys, user):
            raise RuntimeError("Model connection failed")
        capture._original_generate = mock_gen_fail
        client = OllamaClient({"model": "gemma4:e4b"})
        with pytest.raises(RuntimeError, match="Model connection failed"):
            client.generate_content("sys", "user")

    assert capture.generation_calls == 1
    assert capture.token_coverage_complete is False
    assert len(capture.events) == 1
    failed_ev = capture.events[0]
    assert failed_ev["prompt_tokens"] is None
    assert failed_ev["completion_tokens"] is None
    assert failed_ev["total_tokens"] is None

    # Raw control failure in execute_trial_unit
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_gen_exc",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        side_effect=RuntimeError("Ollama HTTP 500 error"),
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value={"status": "fail", "reason": "No files found"},
    ):
        rec = execute_trial_unit(
            plan_unit,
            experiment_id="test-gen-exc",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(rec, "trial_record")
    assert rec["execution"]["generation_calls"] == 1
    assert rec["execution"]["internal_attempts"] == 1
    assert rec["cost"]["primary_prompt_tokens"] is None
    assert rec["cost"]["total_tokens"] is None
    assert rec["validity"]["token_coverage_complete"] is False
    assert rec["verification"]["first_failure_category"] == "generation_error"
    assert rec["validity"]["infrastructure_error"] is None
    assert rec["validity"]["first_verifier_completed"] is True
    assert rec["validity"]["terminal_verifier_completed"] is True
    assert rec["validity"]["verifier_completed"] is True


def test_authoritative_first_verification_verifier_crash_and_no_recovery(
    mock_trial_environment,
) -> None:
    """Verifier crash classifies as verifier_error; no recovery."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_verifier_crash",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_single_recovery",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    with patch.object(
        HostAdapter, "solve", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        side_effect=OSError("Disk I/O error during verification"),
    ):
        rec = execute_trial_unit(
            plan_unit,
            experiment_id="test-verif-crash",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(rec, "trial_record")
    assert rec["verification"]["first_passed"] is False
    assert rec["verification"]["first_failure_category"] == "verifier_error"
    assert rec["verification"]["recovery_eligible"] is False
    assert rec["execution"]["recovery_attempted"] is False
    assert rec["validity"]["first_verifier_completed"] is False
    assert rec["validity"]["terminal_verifier_completed"] is False
    assert rec["validity"]["verifier_completed"] is False
    assert "Disk I/O error" in str(rec["validity"]["infrastructure_error"])


def test_control_once_single_generation_when_application_fails(
    mock_trial_environment,
) -> None:
    """One successful control request + app failure = 1 generation call."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_ctrl_app_fail",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    mock_resp = "```python:legacy_link.py\npass\n```"
    mock_meta = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_seconds": 0.1,
    }

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ) as mock_gen, patch(
        "eval.reliability_matrix_execution.apply_response",
        side_effect=ValueError("Write not permitted for non-allowlisted path"),
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value={"status": "fail", "reason": "No files written"},
    ):
        rec = execute_trial_unit(
            plan_unit,
            experiment_id="test-ctrl-app-fail",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(rec, "trial_record")
    assert mock_gen.call_count == 1
    assert rec["execution"]["generation_calls"] == 1
    assert rec["execution"]["internal_attempts"] == 1
    assert (
        rec["verification"]["first_failure_category"] == "application_error"
    )
    assert rec["validity"]["infrastructure_error"] is None


def test_missing_model_digest_fails_closed_zero_generation(
    mock_trial_environment,
) -> None:
    """Missing or empty model digest fails closed before generation."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    bad_prov = dict(prov_info)
    bad_prov["model_digest"] = ""

    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_missing_digest",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    def poison(*args, **kwargs):
        raise AssertionError("Model must not be called!")

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        side_effect=poison,
    ):
        with pytest.raises(
            RuntimeError,
            match="Ollama provenance unavailable or missing model digest",
        ):
            execute_trial_unit(
                plan_unit,
                experiment_id="test-missing-digest",
                workspace_root=ws_root,
                tasks_dir=tasks_dir,
                output_dir=out_dir,
                provenance_info=bad_prov,
            )


def test_canonical_paths_resolve_from_repo_root(
    mock_trial_environment,
    tmp_path,
) -> None:
    """Canonical model config and adapter resolve relative to repo_root."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_repo_root_test",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_single",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": EXPERIMENT_BASE_SHA,
    }

    empty_root = tmp_path / "empty_repo"
    empty_root.mkdir()
    with pytest.raises(
        FileNotFoundError,
        match="Canonical model config missing",
    ):
        execute_trial_unit(
            plan_unit,
            base_sha=EXPERIMENT_BASE_SHA,
            harness_sha=EXPERIMENT_BASE_SHA,
            experiment_id="test-repo-root",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
            repo_root=empty_root,
        )


def test_primary_execution_exception_cannot_yield_trial_success(
    mock_trial_environment,
) -> None:
    """Primary execution failure cannot become success if verifier passes."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_prim_exc_perm_verif",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    mock_resp = "```python:legacy_link.py\npass\n```"
    mock_meta = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_seconds": 0.1,
    }

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ), patch(
        "eval.reliability_matrix_execution.apply_response",
        side_effect=RuntimeError("Filesystem permission denied"),
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value={"status": "success", "scope": "PASS"},
    ):
        rec = execute_trial_unit(
            plan_unit,
            experiment_id="test-prim-exc-verif-pass",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(rec, "trial_record")
    assert rec["verification"]["first_passed"] is False
    assert rec["verification"]["terminal_passed"] is False
    assert (
        rec["verification"]["first_failure_category"] == "application_error"
    )
    assert rec["verification"]["recovery_eligible"] is False


def test_recovery_reverifier_crash_classified_as_verifier_error(
    mock_trial_environment,
) -> None:
    """Re-verifier crash is verifier_error, not recovery_failed."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_reverif_crash",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_single_recovery",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    first_verif = {"status": "fail", "reason": "Syntax error in unit"}
    calls = 0

    def mock_verify(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return first_verif
        raise OSError("Disk crash during reverify")

    with patch.object(
        HostAdapter, "solve", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        side_effect=mock_verify,
    ), patch(
        "eval.reliability_matrix_execution.execute_recovery_attempt",
        return_value=MagicMock(attempted=True, completed=True),
    ):
        rec = execute_trial_unit(
            plan_unit,
            experiment_id="test-reverif-crash",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(rec, "trial_record")
    assert rec["verification"]["first_passed"] is False
    assert rec["verification"]["terminal_passed"] is False
    assert (
        rec["verification"]["terminal_failure_category"] == "verifier_error"
    )
    assert rec["validity"]["first_verifier_completed"] is True
    assert rec["validity"]["terminal_verifier_completed"] is False
    assert rec["validity"]["verifier_completed"] is False
    assert "Disk crash during reverify" in str(
        rec["validity"]["infrastructure_error"]
    )


def test_stage_aware_response_schema_error_classification(
    mock_trial_environment,
) -> None:
    """Malformed model response at boundary is response_schema_error."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_schema_err",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    mock_resp = "I have thought about the problem and here is advice: ..."
    mock_meta = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_seconds": 0.1,
    }

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value={"status": "fail", "reason": "No files found"},
    ):
        rec = execute_trial_unit(
            plan_unit,
            experiment_id="test-schema-err",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(rec, "trial_record")
    assert (
        rec["verification"]["first_failure_category"]
        == "response_schema_error"
    )
    assert rec["validity"]["infrastructure_error"] is None


def test_infrastructure_invalid_trials_excluded_from_analyzable_denominators(
    mock_trial_environment,
) -> None:
    """Infrastructure-invalid trials are excluded from analyzable totals."""
    from eval.reliability_matrix_execution import execute_matrix_plan

    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan = materialize_p1_plan(tiers=["tier_1"])

    mock_resp = "```python:legacy_link.py\npass\n```"
    mock_meta = {
        "prompt_tokens": 10,
        "completion_tokens": 5,
        "total_tokens": 15,
        "latency_seconds": 0.1,
    }

    call_idx = 0

    def mock_verify(*args, **kwargs):
        nonlocal call_idx
        call_idx += 1
        if call_idx == 1:
            return {"status": "success", "scope": "PASS"}
        elif call_idx == 2:
            return {"status": "fail", "scope": "PASS", "adherence": "FAIL"}
        else:
            raise OSError("Hardware crash")

    preflight_mock = {
        "preflight_passed": True,
        "blocking_reasons": [],
        "ollama_server": {
            "host": "http://localhost:11434",
            "available": True,
            "version": "0.33.2",
            "model": "gemma4:e4b",
            "model_digest": prov_info["model_digest"],
        },
    }

    with patch(
        "eval.reliability_matrix_execution.check_ollama_provenance",
        return_value=prov_info,
    ), patch(
        "eval.reliability_matrix.run_preflight",
        return_value=preflight_mock,
    ), patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ), patch.object(
        HostAdapter, "solve", return_value=None
    ), patch.object(
        HostAdapter, "solve_swarm", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        side_effect=mock_verify,
    ):
        summary = execute_matrix_plan(
            plan,
            workspace_root=ws_root,
            output_dir=out_dir,
            tasks_dir=tasks_dir,
            lock_path=ws_root / "test_lock.file",
        )

    assert summary["status"] == "aborted"
    assert "Hardware crash" in str(summary["stop_reason"])

    arm_stats_swarm = summary["metrics"]["arms"]["mm_swarm"]
    assert arm_stats_swarm["total"] == 1
    assert arm_stats_swarm["analyzable"] == 1
    assert arm_stats_swarm["passed"] == 1
    assert arm_stats_swarm["infrastructure_excluded"] == 0

    arm_stats_ctrl = summary["metrics"]["arms"]["control_once"]
    assert arm_stats_ctrl["total"] == 1
    assert arm_stats_ctrl["analyzable"] == 1
    assert arm_stats_ctrl["passed"] == 0
    assert arm_stats_ctrl["infrastructure_excluded"] == 0

    arm_stats_rec = summary["metrics"]["arms"]["mm_swarm_recovery"]
    assert arm_stats_rec["total"] == 1
    assert arm_stats_rec["analyzable"] == 0
    assert arm_stats_rec["passed"] == 0
    assert arm_stats_rec["infrastructure_excluded"] == 1

    assert summary["metrics"]["total_trials"] == 3
    assert summary["metrics"]["total_analyzable"] == 2
    assert summary["metrics"]["total_passed"] == 1
    assert summary["metrics"]["total_infrastructure_excluded"] == 1


def test_directive_1_frozen_control_prompt_byte_identity() -> None:
    """Prompt template and generated prompts match bare baseline exactly."""
    assert BARE_PROMPT_TEMPLATE == bare_baseline.PROMPT_TEMPLATE

    plan = materialize_p1_plan()
    unique_task_files: list[str] = []
    seen: set[str] = set()
    for u in plan["trial_units"]:
        tf = u["task_file"]
        if tf not in seen:
            seen.add(tf)
            unique_task_files.append(tf)

    expected_task_ids = {"task_003", "task_047", "task_1415"}
    checked_count = 0

    for task_file in unique_task_files:
        task_path = DEFAULT_TASKS_DIR / task_file
        assert task_path.is_file(), f"Configured task file {task_path} missing"
        task_data = json.loads(task_path.read_text(encoding="utf-8"))
        assert task_data["id"] in expected_task_ids

        bare_prompt = bare_baseline.build_prompt(task_data)
        expected = BARE_PROMPT_TEMPLATE.format(
            title=task_data.get("title", task_data["id"]),
            description=task_data["description"],
            constraints=json.dumps(
                task_data.get("constraints", {}), sort_keys=True
            ),
            expected_files=", ".join(task_data.get("expected_files", [])),
        )
        assert bare_prompt == expected
        assert bare_prompt.encode("utf-8") == expected.encode("utf-8")
        assert (
            compute_sha256_bytes(bare_prompt.encode("utf-8"))
            == compute_sha256_bytes(expected.encode("utf-8"))
        )
        checked_count += 1

    assert checked_count == 3


def test_directive_2_plan_validation_cross_field_invariants() -> None:
    """Execution plan validation checks all cross-field invariants."""
    plan = materialize_p1_plan(tiers=["tier_1"])
    validate_execution_plan(plan)

    # 1) Bad base_sha
    bad_plan = copy.deepcopy(plan)
    bad_plan["base_sha"] = "0" * 40
    with pytest.raises(ValueError, match="base SHAs must equal"):
        validate_execution_plan(bad_plan)

    # 2) Bad harness_sha
    bad_plan = copy.deepcopy(plan)
    bad_plan["harness_sha"] = "0" * 40
    with pytest.raises(ValueError, match="harness HEAD"):
        validate_execution_plan(bad_plan)

    # 3) Bad arm_order_seed
    bad_plan = copy.deepcopy(plan)
    bad_plan["arm_order_seed"] = "bad_seed"
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="arm_order_seed",
    ):
        validate_execution_plan(bad_plan)

    # 4) Empty trial_units
    bad_plan = copy.deepcopy(plan)
    bad_plan["trial_units"] = []
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="trial_units",
    ):
        validate_execution_plan(bad_plan)

    # 5) Non-contiguous order_index
    bad_plan = copy.deepcopy(plan)
    bad_plan["trial_units"][1]["order_index"] = 99
    with pytest.raises(ValueError, match="invalid order index"):
        validate_execution_plan(bad_plan)

    # 6) Unsafe trial_id with path traversal
    bad_plan = copy.deepcopy(plan)
    bad_plan["trial_units"][0]["trial_id"] = "../escaped_id"
    with pytest.raises(ValueError, match="unsafe trial_id"):
        validate_execution_plan(bad_plan)

    # 7) Duplicate trial_id
    bad_plan = copy.deepcopy(plan)
    bad_plan["trial_units"][1]["trial_id"] = (
        bad_plan["trial_units"][0]["trial_id"]
    )
    with pytest.raises(ValueError, match="Duplicate trial_id"):
        validate_execution_plan(bad_plan)

    # 8) Invalid deterministic arm order
    bad_plan = copy.deepcopy(plan)
    bad_plan["trial_units"][0]["arm"], bad_plan["trial_units"][1]["arm"] = (
        bad_plan["trial_units"][1]["arm"],
        bad_plan["trial_units"][0]["arm"],
    )
    with pytest.raises(ValueError, match="canonical deterministic order"):
        validate_execution_plan(bad_plan)

    # 9) Unit tier does not match plan tiers
    bad_plan = copy.deepcopy(plan)
    bad_plan["trial_units"][0]["tier"] = "tier_5"
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="does not belong to plan tiers|not match plan tiers",
    ):
        validate_execution_plan(bad_plan)

    # 10) Unit replicate exceeds plan replicates
    bad_plan = copy.deepcopy(plan)
    bad_plan["trial_units"][0]["replicate"] = 2
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="out of range|missing group",
    ):
        validate_execution_plan(bad_plan)

    # 11) Duplicate tier in plan tiers
    bad_plan = copy.deepcopy(plan)
    bad_plan["tiers"] = ["tier_1", "tier_1"]
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="duplicates",
    ):
        validate_execution_plan(bad_plan)

    # 12) Missing complete five-arm group
    bad_plan = copy.deepcopy(plan)
    bad_plan["trial_units"] = bad_plan["trial_units"][:-1]
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="expected 5|has 4 arms|groups",
    ):
        validate_execution_plan(bad_plan)


def test_directive_3_atomic_workspace_freshness(tmp_path: Path) -> None:
    """prepare_fresh_trial_workspace enforces containment and freshness."""
    ws_root = tmp_path / "ws_root"
    ws_root.mkdir()

    # 1) Non-contained path is rejected
    outside = tmp_path / "outside"
    with pytest.raises(ValueError, match="escapes workspace_root"):
        prepare_fresh_trial_workspace(outside, outside, ws_root)

    # 2) Pre-existing trial workspace fails closed
    ws1 = ws_root / "trial_01"
    iso1 = ws_root / "trial_01_iso"
    ws1.mkdir()
    with pytest.raises(FileExistsError, match="Fail closed"):
        prepare_fresh_trial_workspace(ws1, iso1, ws_root)
    assert not iso1.exists()

    # 3) Pre-existing isolation workspace fails closed
    ws2 = ws_root / "trial_02"
    iso2 = ws_root / "trial_02_iso"
    iso2.mkdir()
    with pytest.raises(FileExistsError, match="Fail closed"):
        prepare_fresh_trial_workspace(ws2, iso2, ws_root)
    assert not ws2.exists()

    # 4) Fresh paths succeed and both directories are created
    ws3 = ws_root / "trial_03"
    iso3 = ws_root / "trial_03_iso"
    prepare_fresh_trial_workspace(ws3, iso3, ws_root)
    assert ws3.is_dir()
    assert iso3.is_dir()


def test_directive_5_strict_canonical_verifier_failure_check(
    mock_trial_environment,
) -> None:
    """Verifier must return exact status=='fail' to trigger recovery."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_strict_verif",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_single_recovery",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    # Case A: status is 'error' (not 'fail') -> verifier_error, no recovery
    with patch.object(
        HostAdapter, "solve", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value={"status": "error", "message": "Verifier crash"},
    ), patch(
        "eval.reliability_matrix_execution.execute_recovery_attempt",
    ) as mock_rec:
        rec = execute_trial_unit(
            plan_unit,
            experiment_id="test-strict-verif",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )
    assert rec["verification"]["first_passed"] is False
    assert rec["verification"]["first_failure_category"] == "verifier_error"
    assert rec["verification"]["recovery_eligible"] is False
    mock_rec.assert_not_called()

    # Case B: non-dict returned -> verifier_error, no recovery
    plan_unit_b = copy.deepcopy(plan_unit)
    plan_unit_b["trial_id"] = "trial_strict_verif_nondict"
    with patch.object(
        HostAdapter, "solve", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value="not a dict",
    ), patch(
        "eval.reliability_matrix_execution.execute_recovery_attempt",
    ) as mock_rec:
        rec = execute_trial_unit(
            plan_unit_b,
            experiment_id="test-strict-verif-nondict",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )
    assert rec["verification"]["first_failure_category"] == "verifier_error"
    assert rec["verification"]["recovery_eligible"] is False
    mock_rec.assert_not_called()


def test_directive_6_recovery_executor_exception_boundedness(
    mock_trial_environment,
) -> None:
    """Recovery executor exception is trapped and recorded safely."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_bounded_rec_exc",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "mm_single_recovery",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    first_verif = {"status": "fail", "reason": "First attempt syntax error"}

    with patch.object(
        HostAdapter, "solve", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=first_verif,
    ), patch(
        "eval.reliability_matrix_execution.execute_recovery_attempt",
        side_effect=RuntimeError("Simulated recovery executor crash"),
    ):
        rec = execute_trial_unit(
            plan_unit,
            experiment_id="test-bounded-exc",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    validate_payload_against_schema(rec, "trial_record")
    assert rec["execution"]["recovery_attempted"] is True
    assert rec["execution"]["recovery_completed"] is False
    assert (
        rec["verification"]["terminal_failure_category"] == "recovery_failed"
    )
    assert rec["validity"]["infrastructure_error"] is None


def test_directive_7_raw_response_persistence(tmp_path: Path) -> None:
    """CaptureOllamaUsage persists raw responses and records hashes."""
    out_dir = tmp_path / "output"
    out_dir.mkdir()
    trial_id = "trial_raw_test"

    capture = CaptureOllamaUsage()
    capture.configure_trial(out_dir, trial_id)

    raw_text = "```python:test.py\nprint('hello')\n```"
    capture.record_generation(
        phase="primary",
        raw_response_text=raw_text,
        prompt_tokens=10,
        completion_tokens=5,
    )

    artifacts = capture.raw_response_artifacts
    assert len(artifacts) == 1
    art = artifacts[0]
    assert art["call_index"] == 1
    assert art["phase"] == "primary"
    assert art["relpath"] == f"raw_responses/{trial_id}/call_001_primary.txt"

    disk_file = out_dir / art["relpath"]
    assert disk_file.is_file()
    assert disk_file.read_text(encoding="utf-8") == raw_text
    expected_hash = hashlib.sha256(raw_text.encode("utf-8")).hexdigest()
    assert art["sha256"] == expected_hash


def test_directive_9_and_10_provenance_stop_conditions(
    mock_trial_environment,
) -> None:
    """Model digest mismatch aborts loop immediately with stop_reason."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan = materialize_p1_plan(tiers=["tier_1"])

    preflight_mock = {
        "preflight_passed": True,
        "blocking_reasons": [],
        "ollama_server": {
            "host": "http://localhost:11434",
            "available": True,
            "version": "0.33.2",
            "model": "gemma4:e4b",
            "model_digest": prov_info["model_digest"],
        },
    }

    prov_calls = 0

    def mock_prov(*args, **kwargs):
        nonlocal prov_calls
        prov_calls += 1
        if prov_calls == 1:
            return prov_info
        bad_prov = dict(prov_info)
        bad_prov["model_digest"] = "mutated_digest_12345"
        return bad_prov

    with patch(
        "eval.reliability_matrix_execution.check_ollama_provenance",
        side_effect=mock_prov,
    ), patch(
        "eval.reliability_matrix.run_preflight",
        return_value=preflight_mock,
    ), patch.object(
        HostAdapter, "solve", return_value=None
    ), patch.object(
        HostAdapter, "solve_swarm", return_value=None
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value={"status": "success", "scope": "PASS"},
    ):
        summary = execute_matrix_plan(
            plan,
            workspace_root=ws_root,
            output_dir=out_dir,
            tasks_dir=tasks_dir,
            lock_path=ws_root / "test_lock.file",
        )

    assert summary["status"] == "aborted"
    assert "digest changed" in summary["stop_reason"].lower()
    assert summary["trial_count"] == 1


def test_directive_10_authoritative_frozen_provenance_mismatch(
    mock_trial_environment,
) -> None:
    """execute_trial_unit fails closed if live digest mismatches frozen."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan_unit = {
        "order_index": 0,
        "trial_order_index": 0,
        "trial_id": "trial_digest_mismatch",
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "task_003_legacy_link_circuitbreaker.json",
        "arm": "control_once",
        "replicate": 1,
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": resolve_harness_sha(),
    }

    with pytest.raises(
        RuntimeError,
        match="does not match expected digest",
    ):
        execute_trial_unit(
            plan_unit,
            experiment_id="test-digest-mismatch",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
            expected_digest="different_frozen_digest",
        )


def test_plan_unit_tier_not_in_plan_tiers_fails_closed(
    mock_trial_environment,
) -> None:
    """Plan unit tier differing from plan['tiers'] fails before any run."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    plan = materialize_p1_plan(tiers=["tier_1"])
    corrupt_plan = copy.deepcopy(plan)
    corrupt_plan["trial_units"][0]["tier"] = "tier_5"

    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="does not belong to plan tiers|not match plan tiers",
    ):
        execute_matrix_plan(
            corrupt_plan,
            workspace_root=ws_root,
            output_dir=out_dir,
            tasks_dir=tasks_dir,
            dry_run=True,
        )

    # Ensure zero workspaces or artifacts were created
    trial_ws = ws_root / corrupt_plan["trial_units"][0]["trial_id"]
    assert not trial_ws.exists()
    assert not (out_dir / "run_summary.json").exists()


def test_plan_unit_replicate_exceeds_plan_replicates_fails() -> None:
    """Plan with unit replicate outside 1..plan['replicates'] fails."""
    plan = materialize_p1_plan(tiers=["tier_1"], replicates=1)
    corrupt_plan = copy.deepcopy(plan)
    corrupt_plan["trial_units"][0]["replicate"] = 2
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="out of range|missing group",
    ):
        validate_execution_plan(corrupt_plan)


def test_plan_missing_complete_arm_group_fails() -> None:
    """Plan missing any arm of a canonical 5-arm group fails validation."""
    plan = materialize_p1_plan(tiers=["tier_1"], replicates=1)
    corrupt_plan = copy.deepcopy(plan)
    corrupt_plan["trial_units"] = corrupt_plan["trial_units"][:-1]
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="expected 5|has 4 arms|groups",
    ):
        validate_execution_plan(corrupt_plan)


def test_plan_duplicate_tier_fails() -> None:
    """Plan with duplicate tiers in plan['tiers'] fails validation."""
    plan = materialize_p1_plan(tiers=["tier_1"], replicates=1)
    corrupt_plan = copy.deepcopy(plan)
    corrupt_plan["tiers"] = ["tier_1", "tier_1"]
    with pytest.raises(
        (ValueError, jsonschema.ValidationError),
        match="duplicates",
    ):
        validate_execution_plan(corrupt_plan)


def test_non_repo_cwd_explicit_repo_root_identical_p1_plan(
    tmp_path: Path,
) -> None:
    """Foreign CWD with explicit repo_root materializes identical plan."""
    repo_root = Path(".").resolve()
    canonical_plan = materialize_p1_plan(repo_root=repo_root)

    old_cwd = os.getcwd()
    try:
        os.chdir(tmp_path)
        foreign_plan = materialize_p1_plan(repo_root=repo_root)
        validate_execution_plan(foreign_plan, repo_root=repo_root)
    finally:
        os.chdir(old_cwd)

    assert foreign_plan["harness_sha"] == canonical_plan["harness_sha"]
    assert foreign_plan["tiers"] == canonical_plan["tiers"]
    assert len(foreign_plan["trial_units"]) == len(
        canonical_plan["trial_units"]
    )
    for u_canon, u_foreign in zip(
        canonical_plan["trial_units"], foreign_plan["trial_units"]
    ):
        assert u_canon["tier"] == u_foreign["tier"]
        assert u_canon["task_id"] == u_foreign["task_id"]
        assert u_canon["task_file"] == u_foreign["task_file"]
        assert u_canon["arm"] == u_foreign["arm"]
        assert u_canon["replicate"] == u_foreign["replicate"]
        assert u_canon["order_index"] == u_foreign["order_index"]


def test_canonical_p1_order_and_zero_generation_count() -> None:
    """Canonical 15-unit P1 order unchanged; live generation count is zero."""
    plan = materialize_p1_plan()
    assert len(plan["trial_units"]) == 15
    assert plan["tiers"] == list(P1_TIERS)
    expected_tiers = ["tier_1"] * 5 + ["tier_5"] * 5 + ["tier_7"] * 5
    actual_tiers = [u["tier"] for u in plan["trial_units"]]
    assert actual_tiers == expected_tiers

    capture = CaptureOllamaUsage()
    assert capture.generation_calls == 0
    assert len(ARMS) == 5


def test_p2_plan_cardinality_and_seven_concrete_tiers() -> None:
    """P2 plan produces 28 trial units across 7 tiers, 2 tasks, 2 arms."""
    plan = materialize_p2_plan(check_git_tracking=True)
    assert plan["plan_design"] == P2_PLAN_DESIGN
    assert len(plan["trial_units"]) == 28
    assert plan["tiers"] == list(P2_TIERS)
    assert len(plan["tiers"]) == 7
    assert "tier_2" not in plan["tiers"]
    assert plan["replicates"] == 1

    arms = sorted({u["arm"] for u in plan["trial_units"]})
    assert arms == sorted(P2_ARMS)

    for i, u in enumerate(plan["trial_units"]):
        assert u["order_index"] == i
        assert u["trial_order_index"] == i
        assert u["task_slot"] in (1, 2)
        assert u["replicate"] == 1


def test_p2_two_distinct_tasks_per_tier_and_p1_continuity() -> None:
    """Each concrete tier selects 2 distinct tasks; slot 1 keeps P1 task."""
    cfg = json.loads(
        Path("eval/evaluation_config.json").read_text(encoding="utf-8")
    )
    tiers_cfg = cfg["tiers"]

    for tier in P2_TIERS:
        tasks = tiers_cfg[tier]
        slot1, slot2 = select_deterministic_p2_tasks(
            EXPERIMENT_BASE_SHA, tier, tasks
        )
        assert slot1 != slot2, f"Tier {tier} selected duplicate tasks"

        # Deterministic reproducibility
        s1_again, s2_again = select_deterministic_p2_tasks(
            EXPERIMENT_BASE_SHA, tier, tasks
        )
        assert (slot1, slot2) == (s1_again, s2_again)

    # Verify P1 continuity on shared tiers
    s1_t1, _ = select_deterministic_p2_tasks(
        EXPERIMENT_BASE_SHA, "tier_1", tiers_cfg["tier_1"]
    )
    assert s1_t1 == "task_003_legacy_link_circuitbreaker.json"

    s1_t5, _ = select_deterministic_p2_tasks(
        EXPERIMENT_BASE_SHA, "tier_5", tiers_cfg["tier_5"]
    )
    assert s1_t5 == "task_047_stream_stack_enricher.json"

    s1_t7, _ = select_deterministic_p2_tasks(
        EXPERIMENT_BASE_SHA, "tier_7", tiers_cfg["tier_7"]
    )
    assert s1_t7 == "task_1415_file_proxy_retry.json"


def test_p2_rejects_rollup_tier() -> None:
    """P2 materialization fails closed if given rollup tier like tier_2."""
    with pytest.raises(ValueError, match="rollup tier"):
        materialize_p2_plan(tiers=["tier_1", "tier_2"])


def test_p2_rejects_unsupported_arms() -> None:
    """P2 materialization rejects arms outside P2_ARMS."""
    with pytest.raises(ValueError, match="strictly rejects unsupported arms"):
        materialize_p2_plan(arms=["control_once", "mm_single", "mm_swarm"])


def test_p2_rejects_non_baseline_tracked_task(tmp_path: Path) -> None:
    """P2 fails closed if task selected is not tracked in baseline Git."""
    dummy_cfg = {
        "tiers": {
            "tier_1": [
                "task_9999_untracked.json",
                "task_001_legacy_registry_ratelimiter.json",
            ]
        }
    }
    cfg_file = tmp_path / "evaluation_config.json"
    cfg_file.write_text(json.dumps(dummy_cfg), encoding="utf-8")

    with pytest.raises((ValueError, FileNotFoundError)):
        materialize_p2_plan(
            config_path=cfg_file,
            tiers=["tier_1"],
            check_git_tracking=True,
        )


def test_p2_duplicate_prevention_and_stable_ordering() -> None:
    """P2 rejects duplicate trial units or invalid order indices."""
    plan = materialize_p2_plan(check_git_tracking=True)
    validate_execution_plan(plan)

    # Check duplicate trial ID
    corrupt = copy.deepcopy(plan)
    corrupt["trial_units"][1]["trial_id"] = corrupt["trial_units"][0][
        "trial_id"
    ]
    with pytest.raises(ValueError, match="Duplicate trial_id"):
        validate_execution_plan(corrupt)

    # Check duplicate unit tuple
    corrupt2 = copy.deepcopy(plan)
    corrupt2["trial_units"][1]["arm"] = corrupt2["trial_units"][0]["arm"]
    with pytest.raises(ValueError, match="Duplicate unit tuple"):
        validate_execution_plan(corrupt2)


def test_p2_zero_generation_materialization() -> None:
    """P2 materialization and validation executes zero model generations."""
    capture = CaptureOllamaUsage()
    assert capture.generation_calls == 0

    plan = materialize_p2_plan(check_git_tracking=True)
    validate_execution_plan(plan)

    assert capture.generation_calls == 0


def test_raw_response_path_anchored_across_cwd_mutation(
    tmp_path: Path,
) -> None:
    """CaptureOllamaUsage raw responses land in canonical output tree."""
    out_dir = tmp_path / "eval" / "results" / "m12" / "test-run"
    ws_dir = tmp_path / "workspaces" / "trial_01"
    ws_dir.mkdir(parents=True, exist_ok=True)

    capture = CaptureOllamaUsage(output_dir=out_dir, trial_id="trial_01")
    old_cwd = os.getcwd()
    try:
        os.chdir(ws_dir)
        capture.record_generation(
            phase="primary",
            raw_response_text="Test response payload",
            prompt_tokens=10,
            completion_tokens=20,
        )
    finally:
        os.chdir(old_cwd)

    # Assert artifact exists in canonical output tree
    expected_file = (
        out_dir / "raw_responses" / "trial_01" / "call_001_primary.txt"
    )
    assert expected_file.is_file()
    assert (
        expected_file.read_text(encoding="utf-8") == "Test response payload"
    )

    # Assert workspace contains zero raw_responses
    ws_raw = (
        ws_dir / "eval" / "results" / "m12" / "test-run" / "raw_responses"
    )
    assert not ws_raw.exists()
    assert not (ws_dir / "raw_responses").exists()


def test_p1_materialization_and_semantics_strictly_unchanged() -> None:
    """P1 materialization output remains unchanged with 15 units, 3 tiers."""
    p1 = materialize_p1_plan()
    validate_execution_plan(p1)
    assert len(p1["trial_units"]) == 15
    assert p1["tiers"] == list(P1_TIERS)
    assert "plan_design" not in p1 or p1.get("plan_design") is None
    for u in p1["trial_units"]:
        assert "task_slot" not in u
