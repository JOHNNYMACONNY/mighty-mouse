"""Tests for eval/reliability_matrix_execution.py and five-arm engine."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import threading
from unittest.mock import MagicMock, patch

import pytest

from eval.reliability_matrix import (
    EXPERIMENT_BASE_SHA,
    SCHEMA_VERSION,
    SWARM_CONCURRENCY,
    resolve_harness_sha,
    run_preflight,
    validate_payload_against_schema,
    verify_baseline_harness_delta,
)
from eval.reliability_matrix_execution import (
    ARM_ORDER_SEED_PREFIX,
    CaptureOllamaUsage,
    classify_failure,
    deterministic_arm_order,
    execute_matrix_plan,
    execute_trial_unit,
    materialize_p1_plan,
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
        with patch.object(
            HostAdapter,
            "resolve_ollama_model_digest",
            return_value=test_digest,
        ):
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
    harness_sha = resolve_harness_sha()
    mini_plan = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": "test-mini-run",
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": harness_sha,
        "replicates": 1,
        "tiers": ["tier_1"],
        "trial_units": [
            {
                "order_index": 0,
                "trial_order_index": 0,
                "trial_id": "mini_trial_01",
                "tier": "tier_1",
                "task_id": "task_003",
                "task_file": "task_003_legacy_link_circuitbreaker.json",
                "arm": "control_once",
                "replicate": 1,
                "experiment_base_sha": EXPERIMENT_BASE_SHA,
                "harness_sha": harness_sha,
            }
        ],
        "arm_order_seed": ARM_ORDER_SEED_PREFIX,
        "timestamp": "2026-09-02T20:00:00Z",
    }

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

    with patch(
        "eval.reliability_matrix_execution.request_control_generation",
        return_value=(mock_resp, mock_meta),
    ), patch(
        "eval.reliability_matrix_execution.verify_task",
        return_value=pass_verif,
    ), patch(
        "eval.reliability_matrix_execution.check_ollama_provenance",
        return_value=prov_info,
    ), patch(
        "eval.reliability_matrix.run_preflight",
        return_value={"preflight_passed": True, "blocking_reasons": []},
    ):
        summary = execute_matrix_plan(
            mini_plan,
            workspace_root=ws_root,
            output_dir=out_dir,
            tasks_dir=tasks_dir,
            lock_path=ws_root / "lock.file",
        )

    validate_payload_against_schema(summary, "run_summary")
    assert summary["trial_count"] == 1
    assert summary["metrics"]["total_passed"] == 1
    assert (out_dir / "run_summary.json").is_file()
    assert (out_dir / "mini_trial_01.json").is_file()


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
    monkeypatch.setattr(
        HostAdapter,
        "resolve_ollama_model_digest",
        lambda m: digest,
    )

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


def test_fresh_workspace_purges_stale_files(
    mock_trial_environment,
) -> None:
    """Trial execution purges stale files and starts empty."""
    from eval.reliability_matrix_execution import prepare_fresh_trial_workspace

    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    trial_id = "trial_fresh_ws_test"
    target_ws = ws_root / trial_id
    target_ws.mkdir(parents=True, exist_ok=True)
    stale_file = target_ws / "stale_output.py"
    stale_file.write_text("# stale code from previous run", encoding="utf-8")

    prepare_fresh_trial_workspace(target_ws)
    assert target_ws.is_dir()
    assert not stale_file.exists()
    assert list(target_ws.iterdir()) == []

    # Verify execute_trial_unit also cleans pre-existing workspace
    stale_file.write_text("# new stale content", encoding="utf-8")
    assert stale_file.is_file()

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
        record = execute_trial_unit(
            plan_unit,
            experiment_id="test-fresh-run",
            workspace_root=ws_root,
            tasks_dir=tasks_dir,
            output_dir=out_dir,
            provenance_info=prov_info,
        )

    assert record["verification"]["terminal_passed"] is True
    assert not stale_file.exists()
    # Workspace should not have harness artifacts
    assert not (target_ws / "task.json").exists()
    assert not (target_ws / "model_config.yaml").exists()
    assert not (target_ws / ".mighty-mouse").exists()
    assert (target_ws / "legacy_link.py").exists()


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
    harness_sha = resolve_harness_sha()
    mini_plan = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": "test-dry-run",
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": harness_sha,
        "replicates": 1,
        "tiers": ["tier_1"],
        "trial_units": [
            {
                "order_index": 0,
                "trial_order_index": 0,
                "trial_id": "dry_trial_01",
                "tier": "tier_1",
                "task_id": "task_003",
                "task_file": "task_003_legacy_link_circuitbreaker.json",
                "arm": "control_once",
                "replicate": 1,
                "experiment_base_sha": EXPERIMENT_BASE_SHA,
                "harness_sha": harness_sha,
            }
        ],
        "arm_order_seed": ARM_ORDER_SEED_PREFIX,
        "timestamp": "2026-09-02T20:00:00Z",
    }

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
            mini_plan,
            workspace_root=ws_root,
            output_dir=out_dir,
            tasks_dir=tasks_dir,
            lock_path=ws_root / "lock.file",
            dry_run=True,
        )

    validate_payload_against_schema(summary, "run_summary")
    assert summary["dry_run"] is True
    assert summary["trial_count"] == 0
    assert summary["metrics"]["total_passed"] == 0
    assert summary["metrics"]["total_tokens"] is None


def test_scoped_preflight_gate_stops_execution(
    mock_trial_environment,
) -> None:
    """execute_matrix_plan aborts before trials if preflight fails."""
    ws_root, out_dir, tasks_dir, prov_info = mock_trial_environment
    harness_sha = resolve_harness_sha()
    mini_plan = {
        "schema_version": SCHEMA_VERSION,
        "experiment_id": "test-preflight-fail",
        "experiment_base_sha": EXPERIMENT_BASE_SHA,
        "base_sha": EXPERIMENT_BASE_SHA,
        "harness_sha": harness_sha,
        "replicates": 1,
        "tiers": ["tier_1"],
        "trial_units": [
            {
                "order_index": 0,
                "trial_order_index": 0,
                "trial_id": "fail_trial_01",
                "tier": "tier_1",
                "task_id": "task_003",
                "task_file": "task_003_legacy_link_circuitbreaker.json",
                "arm": "control_once",
                "replicate": 1,
                "experiment_base_sha": EXPERIMENT_BASE_SHA,
                "harness_sha": harness_sha,
            }
        ],
        "arm_order_seed": ARM_ORDER_SEED_PREFIX,
        "timestamp": "2026-09-02T20:00:00Z",
    }

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
                mini_plan,
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
    assert "Ollama HTTP 500" in str(rec["validity"]["infrastructure_error"])


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
    assert rec["validity"]["verifier_completed"] is False
    assert "Disk I/O error" in str(rec["validity"]["infrastructure_error"])
