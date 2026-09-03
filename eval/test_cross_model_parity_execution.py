"""Tests for M13 12-Trial Cross-Model Parity Executor v1 (Ticket 04).

Validates provenance separation, locking, candidate runtime projection,
trial execution seams, authoritative verification, stop conditions,
schema conformance, and dry-run zero-generation guarantees.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile
from typing import Any, Dict
from unittest.mock import MagicMock, patch
import pytest

from eval.cross_model_parity import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_CONTRACT_PATH,
    FROZEN_CANDIDATES,
    LOCK_FILE_PATH,
    M13_EXECUTION_BASE_SHA,
    M13_EXPERIMENT_BASE_SHA,
    M13_EXPERIMENT_ID,
    CrossModelPlanUnit,
    get_current_git_sha,
    materialize_execution_plan,
    verify_base_to_harness_delta,
)
from eval.cross_model_parity_execution import (
    execute_cross_model_plan,
    execute_trial_unit,
    prepare_candidate_runtime,
)
from mighty_mouse.host.adapter import (
    ADAPTER_CONFIG_FILENAME,
    AdapterRuntimeContext,
    HostAdapter,
    MCP_TOOL_CONTRACT_VERSION,
)
from mighty_mouse_mcp.server import _get_mcp_tool_signatures


@pytest.fixture
def mock_local_context() -> AdapterRuntimeContext:
    sigs = _get_mcp_tool_signatures()
    return HostAdapter.resolve_adapter_context(
        ".",
        state_dir=".mighty-mouse",
        tool_signatures=sigs,
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )


# --- 1. Provenance separation ---


def test_provenance_experiment_base_remains_frozen() -> None:
    assert (
        M13_EXPERIMENT_BASE_SHA
        == "e396d1960208673679d7aac8d2f9e6f5d10f2545"
    )


def test_provenance_execution_base_is_ci_stability_sha() -> None:
    assert (
        M13_EXECUTION_BASE_SHA
        == "751d5094ccb472ccdaf65fc967405913f0136e09"
    )


def test_plan_units_bind_experiment_base_sha() -> None:
    plan = materialize_execution_plan()
    units = plan["trial_units"]
    assert len(units) == 12
    for unit in units:
        assert unit["experiment_base_sha"] == M13_EXPERIMENT_BASE_SHA


def test_pr110_not_treated_as_unauthorized_from_execution_base() -> None:
    with patch(
        "subprocess.check_output",
        return_value="eval/cross_model_parity.py\n",
    ):
        paths = verify_base_to_harness_delta(
            base_sha=M13_EXECUTION_BASE_SHA,
            harness_sha=get_current_git_sha(),
        )
        assert paths == ["eval/cross_model_parity.py"]


def test_disallowed_file_outside_m13_harness_fails_closed() -> None:
    with patch(
        "subprocess.check_output",
        return_value="src/mighty_mouse/orchestrator/agent.py\n",
    ):
        with pytest.raises(ValueError, match="Unauthorized file changes"):
            verify_base_to_harness_delta(
                base_sha=M13_EXECUTION_BASE_SHA,
                harness_sha=get_current_git_sha(),
            )


# --- 2. Locking & Preflight ---


def test_preflight_lock_already_held_does_not_double_acquire() -> None:
    from eval.cross_model_parity import run_preflight

    with patch("eval.cross_model_parity.SingleInstanceLock") as mock_lock:
        with patch("eval.cross_model_parity.check_git_clean_except_prototype"):
            with patch(
                "eval.cross_model_parity.verify_base_to_harness_delta",
                return_value=[],
            ):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"version": "0.33.2"}'
                mock_resp.__enter__.return_value = mock_resp
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    run_preflight(lock_already_held=True)
                    mock_lock.assert_not_called()


def test_dry_run_performs_zero_generations() -> None:
    plan = materialize_execution_plan()
    with patch(
        "eval.cross_model_parity_execution.request_control_generation"
    ) as mock_control_gen:
        with patch(
            "mighty_mouse.host.adapter.HostAdapter.solve"
        ) as mock_solve:
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                with patch(
                    "eval.cross_model_parity.verify_base_to_harness_delta",
                    return_value=[],
                ):
                    with patch(
                        "eval.cross_model_parity_execution."
                        "verify_base_to_harness_delta",
                        return_value=[],
                    ):
                        summary = execute_cross_model_plan(
                            plan,
                            dry_run=True,
                        )
                        assert summary["status"] == "dry_run"
                        assert summary["generation_calls"] == 0
                        assert summary["executed_trial_count"] == 0
                        assert summary["planned_trial_count"] == 12
                        mock_control_gen.assert_not_called()
                        mock_solve.assert_not_called()


# --- 3. Candidate Runtime ---


def test_llama_runtime_projection(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    cand = FROZEN_CANDIDATES["llama31_8b_q4km"]
    with tempfile.TemporaryDirectory() as tmp:
        support_dir = Path(tmp)
        p_cfg, p_sha, a_cfg, a_sha = prepare_candidate_runtime(
            cand, mock_local_context, support_dir
        )
        assert p_cfg.exists()
        assert a_cfg.name == ADAPTER_CONFIG_FILENAME
        data = json.loads(a_cfg.read_text(encoding="utf-8"))
        assert data["model_class"] == mock_local_context.model_class
        assert cand.model_class == "llama3.1-8b-local"
        assert data["effective_context_limit"] == 32768
        assert data["ollama_model"] == cand.model_tag
        assert data["model_digest"] == cand.model_digest


def test_qwen_runtime_projection(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    cand = FROZEN_CANDIDATES["qwen25_7b_q4km"]
    with tempfile.TemporaryDirectory() as tmp:
        support_dir = Path(tmp)
        p_cfg, p_sha, a_cfg, a_sha = prepare_candidate_runtime(
            cand, mock_local_context, support_dir
        )
        assert p_cfg.exists()
        assert a_cfg.name == ADAPTER_CONFIG_FILENAME
        data = json.loads(a_cfg.read_text(encoding="utf-8"))
        assert data["model_class"] == mock_local_context.model_class
        assert cand.model_class == "qwen2.5-7b-local"
        assert data["effective_context_limit"] == 32768
        assert data["ollama_model"] == cand.model_tag
        assert data["model_digest"] == cand.model_digest


def test_candidate_digest_mismatch_fails_before_generation(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    plan = materialize_execution_plan()
    unit = plan["trial_units"][0]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        with patch(
            "mighty_mouse.host.adapter.HostAdapter."
            "resolve_ollama_model_digest",
            return_value="sha256:" + "0" * 64,
        ):
            with pytest.raises(ValueError, match="digest unstable or changed"):
                execute_trial_unit(
                    unit,
                    workspace_root=root / "work",
                    support_root=root / "supp",
                    output_dir=root / "out",
                    local_adapter_context=mock_local_context,
                )


# --- 4. Trial Execution Seams ---


def test_control_once_trial_execution_hermetic(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    plan = materialize_execution_plan()
    control_unit = next(
        u for u in plan["trial_units"] if u["arm"] == "control_once"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "out"
        out_dir.mkdir(parents=True)

        mock_gen = (
            "```python\n# solution\n```",
            {
                "prompt_tokens": 150,
                "completion_tokens": 50,
                "total_tokens": 200,
                "latency_seconds": 1.25,
            },
        )
        with patch(
            "eval.cross_model_parity_execution.request_control_generation",
            return_value=mock_gen,
        ) as mock_req:
            with patch(
                "eval.cross_model_parity_execution._apply_response",
                return_value=[Path("solution.py")],
            ):
                with patch(
                    "eval.cross_model_parity_execution.verify_task",
                    return_value={"status": "success"},
                ):
                    rec = execute_trial_unit(
                        control_unit,
                        workspace_root=root / "work",
                        support_root=root / "supp",
                        output_dir=out_dir,
                        local_adapter_context=mock_local_context,
                    )
                    assert rec["arm"] == "control_once"
                    assert rec["passed"] is True
                    assert rec["verifier_completed"] is True
                    assert rec["prompt_tokens"] == 150
                    assert rec["completion_tokens"] == 50
                    assert rec["total_tokens"] == 200
                    assert rec["generation_call_count"] == 1
                    assert rec["swarm_enabled"] is False
                    assert rec["recovery_enabled"] is False
                    assert len(rec["raw_response_relpaths"]) == 1
                    mock_req.assert_called_once()


def test_mm_single_trial_execution_hermetic(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    plan = materialize_execution_plan()
    mm_unit = next(
        u for u in plan["trial_units"] if u["arm"] == "mm_single"
    )
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "out"
        out_dir.mkdir(parents=True)

        with patch(
            "mighty_mouse.host.adapter.HostAdapter.solve"
        ) as mock_solve:
            with patch(
                "eval.cross_model_parity_execution.verify_task",
                return_value={"status": "success"},
            ):
                rec = execute_trial_unit(
                    mm_unit,
                    workspace_root=root / "work",
                    support_root=root / "supp",
                    output_dir=out_dir,
                    local_adapter_context=mock_local_context,
                )
                assert rec["arm"] == "mm_single"
                assert rec["passed"] is True
                assert rec["swarm_enabled"] is False
                assert rec["recovery_enabled"] is False
                mock_solve.assert_called_once()


def test_verifier_crash_becomes_infrastructure_error(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    plan = materialize_execution_plan()
    unit = plan["trial_units"][0]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "out"
        out_dir.mkdir(parents=True)

        with patch("mighty_mouse.host.adapter.HostAdapter.solve"):
            with patch(
                "eval.cross_model_parity_execution.verify_task",
                side_effect=RuntimeError("Docker daemon offline"),
            ):
                rec = execute_trial_unit(
                    unit,
                    workspace_root=root / "work",
                    support_root=root / "supp",
                    output_dir=out_dir,
                    local_adapter_context=mock_local_context,
                )
                assert rec["infrastructure_error"] is True
                assert rec["failure_category"] == "verifier_error"
                assert rec["passed"] is False


# --- 5. Full Plan Execution (Mocked) ---


def test_mocked_plan_runs_all_12_units_in_exact_order() -> None:
    plan = materialize_execution_plan()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "pilot_out"
        work_root = root / "workspaces"

        executed_order: list[int] = []

        def fake_exec(
            unit: CrossModelPlanUnit, **kwargs: Any
        ) -> Dict[str, Any]:
            executed_order.append(unit.order_index)
            return {
                "schema_version": "1.0.0",
                "experiment_id": M13_EXPERIMENT_ID,
                "trial_id": unit.trial_id,
                "order_index": unit.order_index,
                "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
                "execution_base_sha": M13_EXECUTION_BASE_SHA,
                "harness_sha": unit.harness_sha,
                "candidate_id": unit.candidate_id,
                "arm": unit.arm,
                "replicate": 1,
                "model_tag": unit.model_tag,
                "model_family": unit.model_family,
                "model_class": unit.model_class,
                "model_digest": unit.model_digest,
                "quantization": unit.quantization,
                "packaged_context": unit.packaged_context,
                "effective_context": 32768,
                "tier": unit.tier,
                "task_id": unit.task_id,
                "task_file": unit.task_file,
                "task_sha256": unit.task_sha256,
                "ollama_version": "0.33.2",
                "projected_config_sha256": unit.projected_config_sha256,
                "ephemeral_adapter_config_sha256": None,
                "execution_profile_id": None,
                "tool_contract_digest": None,
                "prompt_template_digest": None,
                "runtime_kind": None,
                "runtime_version": None,
                "runtime_model_class": (
                    "local-small" if unit.arm == "mm_single" else None
                ),
                "execution_base_to_harness_changed_paths": [],
                "generation_call_count": 1,
                "output_paths": [],
                "swarm_enabled": False,
                "recovery_enabled": False,
                "recovery_attempted": False,
                "verifier_completed": True,
                "passed": True,
                "failure_category": None,
                "verifier_payload": {"status": "success"},
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "model_latency_seconds": 1.0,
                "wall_latency_seconds": 1.1,
                "provenance_complete": True,
                "token_coverage_complete": True,
                "infrastructure_error": False,
                "trace_artifact_relpath": None,
                "trace_artifact_sha256": None,
                "raw_response_relpaths": [],
                "raw_response_sha256s": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        with patch(
            "eval.cross_model_parity_execution.execute_trial_unit",
            side_effect=fake_exec,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                with patch(
                    "eval.cross_model_parity.verify_base_to_harness_delta",
                    return_value=[],
                ):
                    with patch(
                        "eval.cross_model_parity_execution."
                        "verify_base_to_harness_delta",
                        return_value=[],
                    ):
                        summary = execute_cross_model_plan(
                            plan,
                            output_dir=out_dir,
                            workspace_root=work_root,
                        )
                        assert summary["status"] == "completed"
                        assert summary["executed_trial_count"] == 12
                        assert summary["total_passed"] == 12
                        assert executed_order == list(range(12))
                        assert (out_dir / "run_summary.json").exists()
                        trial_files = list((out_dir / "trials").glob("*.json"))
                        assert len(trial_files) == 12


def test_existing_output_dir_fails_closed() -> None:
    plan = materialize_execution_plan()
    with tempfile.TemporaryDirectory() as tmp:
        existing_dir = Path(tmp) / "already_here"
        existing_dir.mkdir()
        with pytest.raises(FileExistsError, match="already exists"):
            execute_cross_model_plan(
                plan,
                output_dir=existing_dir,
                workspace_root=Path(tmp) / "work",
            )


# --- Additional Requirement Tests ---


def test_plan_sort_order_remains_deterministic_12_units() -> None:
    plan = materialize_execution_plan()
    units = plan["trial_units"]
    assert len(units) == 12
    # Verify exact deterministic order indices
    assert [u["order_index"] for u in units] == list(range(12))
    # Verify unique trial IDs
    assert len(set(u["trial_id"] for u in units)) == 12


def test_stale_harness_sha_rejected_in_plan_validation() -> None:
    plan = materialize_execution_plan()
    from eval.cross_model_parity import validate_execution_plan
    # Provide a mismatched harness SHA
    bad_sha = "0" * 40
    res = validate_execution_plan(plan, current_head=bad_sha)
    assert res["valid"] is False
    assert any("harness_sha mismatch" in err for err in res["errors"])


def test_executor_acquires_canonical_shared_lock() -> None:
    plan = materialize_execution_plan()
    with patch(
        "eval.cross_model_parity_execution.SingleInstanceLock"
    ) as mock_lock:
        with patch("eval.cross_model_parity.check_git_clean_except_prototype"):
            with patch(
                "eval.cross_model_parity.verify_base_to_harness_delta",
                return_value=[],
            ):
                with patch(
                    "eval.cross_model_parity_execution."
                    "verify_base_to_harness_delta",
                    return_value=[],
                ):
                    execute_cross_model_plan(plan, dry_run=True)
                    mock_lock.assert_called_once_with(LOCK_FILE_PATH)


def test_candidate_projected_config_changes_only_model(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    from eval.cross_model_parity import project_candidate_config
    import yaml

    canon = yaml.safe_load(DEFAULT_CONFIG_PATH.read_text(encoding="utf-8"))
    for cand in FROZEN_CANDIDATES.values():
        proj, sha = project_candidate_config(cand.model_tag)
        diff_keys = [k for k in proj if proj[k] != canon.get(k)]
        assert diff_keys == ["model"]
        assert proj["model"] == cand.model_tag


def test_candidate_projected_config_sha_equals_plan_unit_sha() -> None:
    plan = materialize_execution_plan()
    for unit in plan["trial_units"]:
        if unit["arm"] == "mm_single":
            cand = FROZEN_CANDIDATES[unit["candidate_id"]]
            from eval.cross_model_parity import project_candidate_config
            _, expected_sha = project_candidate_config(cand.model_tag)
            assert unit["projected_config_sha256"] == expected_sha
        else:
            assert unit["projected_config_sha256"] is None


def test_canonical_repo_config_and_state_unmodified(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    canon_bytes_before = DEFAULT_CONFIG_PATH.read_bytes()
    adapter_bytes_before = (
        Path(".mighty-mouse") / ADAPTER_CONFIG_FILENAME
    ).read_bytes()

    cand = FROZEN_CANDIDATES["llama31_8b_q4km"]
    with tempfile.TemporaryDirectory() as tmp:
        support_dir = Path(tmp)
        prepare_candidate_runtime(cand, mock_local_context, support_dir)

    assert DEFAULT_CONFIG_PATH.read_bytes() == canon_bytes_before
    assert (
        Path(".mighty-mouse") / ADAPTER_CONFIG_FILENAME
    ).read_bytes() == adapter_bytes_before


def test_wrong_candidate_model_class_fails_validation() -> None:
    from mighty_mouse.host.adapter import HostAdapter
    bad_cfg = {
        "schema_version": "1.0.0",
        "repository": "JOHNNYMACONNY/mighty-mouse",
        "model_digest": FROZEN_CANDIDATES["llama31_8b_q4km"].model_digest,
        "model_class": "unauthorized_model_class",
        "model_source": "ollama",
        "ollama_model": FROZEN_CANDIDATES["llama31_8b_q4km"].model_tag,
        "runtime_kind": "antigravity",
        "runtime_version": "1.0.0",
        "effective_context_limit": 32768,
        "tool_contract_digest": "sha256:" + "0" * 64,
        "prompt_template_digest": "sha256:" + "0" * 64,
        "execution_profile_id": "test_profile",
    }
    with pytest.raises(ValueError):
        HostAdapter.validate_adapter_config(
            bad_cfg, tool_signatures=_get_mcp_tool_signatures()
        )


def test_control_generation_options_fixed() -> None:
    from eval.reliability_matrix_execution import request_control_generation
    mock_resp = MagicMock()
    mock_resp.read.return_value = (
        b'{"response": "ok", "prompt_eval_count": 10, "eval_count": 5}'
    )
    mock_resp.__enter__.return_value = mock_resp

    with patch(
        "urllib.request.urlopen", return_value=mock_resp
    ) as mock_urlopen:
        request_control_generation(
            prompt="test",
            model="llama3.1:8b-instruct-q4_K_M",
            host="http://127.0.0.1:11434",
            timeout_sec=10,
        )
        req = mock_urlopen.call_args[0][0]
        data = json.loads(req.data.decode("utf-8"))
        assert data["options"]["temperature"] == 0.2
        assert data["options"]["num_predict"] == 4000
        assert data["options"]["num_ctx"] == 32768


def test_ordinary_verifier_fail_becomes_analyzable(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    plan = materialize_execution_plan()
    unit = plan["trial_units"][0]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "out"
        out_dir.mkdir(parents=True)

        with patch("mighty_mouse.host.adapter.HostAdapter.solve"):
            with patch(
                "eval.cross_model_parity_execution.verify_task",
                return_value={"status": "fail", "scope": "FAIL"},
            ):
                rec = execute_trial_unit(
                    unit,
                    workspace_root=root / "work",
                    support_root=root / "supp",
                    output_dir=out_dir,
                    local_adapter_context=mock_local_context,
                )
                assert rec["infrastructure_error"] is False
                assert rec["passed"] is False
                assert rec["failure_category"] == "scope_failure"


def test_fresh_workspace_collision_fails_closed(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    plan = materialize_execution_plan()
    unit = plan["trial_units"][0]
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "out"
        out_dir.mkdir(parents=True)

        # Pre-create the workspace so collision occurs
        pre_existing = root / "work" / unit["trial_id"] / "workspace"
        pre_existing.mkdir(parents=True)

        with pytest.raises(FileExistsError, match="already exists"):
            execute_trial_unit(
                unit,
                workspace_root=root / "work",
                support_root=root / "supp",
                output_dir=out_dir,
                local_adapter_context=mock_local_context,
            )


def test_ordinary_failure_does_not_abort_subsequent_trials() -> None:
    plan = materialize_execution_plan()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "pilot_out"
        work_root = root / "workspaces"

        executed_order: list[int] = []

        def fake_exec_fail_first(
            unit: CrossModelPlanUnit, **kwargs: Any
        ) -> Dict[str, Any]:
            executed_order.append(unit.order_index)
            # First trial fails benchmark, subsequent pass
            passed = unit.order_index != 0
            fail_cat = None if passed else "test_failure"
            return {
                "schema_version": "1.0.0",
                "experiment_id": M13_EXPERIMENT_ID,
                "trial_id": unit.trial_id,
                "order_index": unit.order_index,
                "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
                "execution_base_sha": M13_EXECUTION_BASE_SHA,
                "harness_sha": unit.harness_sha,
                "candidate_id": unit.candidate_id,
                "arm": unit.arm,
                "replicate": 1,
                "model_tag": unit.model_tag,
                "model_family": unit.model_family,
                "model_class": unit.model_class,
                "model_digest": unit.model_digest,
                "quantization": unit.quantization,
                "packaged_context": unit.packaged_context,
                "effective_context": 32768,
                "tier": unit.tier,
                "task_id": unit.task_id,
                "task_file": unit.task_file,
                "task_sha256": unit.task_sha256,
                "ollama_version": "0.33.2",
                "projected_config_sha256": unit.projected_config_sha256,
                "ephemeral_adapter_config_sha256": None,
                "execution_profile_id": None,
                "tool_contract_digest": None,
                "prompt_template_digest": None,
                "runtime_kind": None,
                "runtime_version": None,
                "runtime_model_class": (
                    "local-small" if unit.arm == "mm_single" else None
                ),
                "execution_base_to_harness_changed_paths": [],
                "generation_call_count": 1,
                "output_paths": [],
                "swarm_enabled": False,
                "recovery_enabled": False,
                "recovery_attempted": False,
                "verifier_completed": True,
                "passed": passed,
                "failure_category": fail_cat,
                "verifier_payload": {
                    "status": "success" if passed else "fail"
                },
                "prompt_tokens": 100,
                "completion_tokens": 50,
                "total_tokens": 150,
                "model_latency_seconds": 1.0,
                "wall_latency_seconds": 1.1,
                "provenance_complete": True,
                "token_coverage_complete": True,
                "infrastructure_error": False,
                "trace_artifact_relpath": None,
                "trace_artifact_sha256": None,
                "raw_response_relpaths": [],
                "raw_response_sha256s": [],
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

        with patch(
            "eval.cross_model_parity_execution.execute_trial_unit",
            side_effect=fake_exec_fail_first,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                with patch(
                    "eval.cross_model_parity.verify_base_to_harness_delta",
                    return_value=[],
                ):
                    with patch(
                        "eval.cross_model_parity_execution."
                        "verify_base_to_harness_delta",
                        return_value=[],
                    ):
                        summary = execute_cross_model_plan(
                            plan,
                            output_dir=out_dir,
                            workspace_root=work_root,
                        )
                        assert summary["status"] == "completed"
                        assert summary["executed_trial_count"] == 12
                        assert summary["total_passed"] == 11
                        assert summary["total_analyzable"] == 12
                        assert len(executed_order) == 12


def test_provenance_drift_aborts_run() -> None:
    plan = materialize_execution_plan()
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        out_dir = root / "pilot_out"
        work_root = root / "workspaces"

        call_count = 0

        def side_effect_digest(tag: str) -> str:
            nonlocal call_count
            call_count += 1
            if "gemma" in tag:
                return (
                    "sha256:4c27e0f5b5adf02ac956c7322bd2ee7636fe3f45"
                    "a8512c9aba5385242cb6e09a"
                )
            if call_count <= 5:
                return (
                    FROZEN_CANDIDATES["llama31_8b_q4km"].model_digest
                    if "llama" in tag
                    else FROZEN_CANDIDATES["qwen25_7b_q4km"].model_digest
                )
            return "sha256:" + "f" * 64

        with patch(
            "mighty_mouse.host.adapter.HostAdapter."
            "resolve_ollama_model_digest",
            side_effect=side_effect_digest,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                with patch(
                    "eval.cross_model_parity.verify_base_to_harness_delta",
                    return_value=[],
                ):
                    with patch(
                        "eval.cross_model_parity_execution."
                        "verify_base_to_harness_delta",
                        return_value=[],
                    ):
                        summary = execute_cross_model_plan(
                            plan,
                            output_dir=out_dir,
                            workspace_root=work_root,
                        )
                        assert summary["status"] == "aborted"
                        assert "Model digest changed" in summary["stop_reason"]
                        assert summary["executed_trial_count"] == 0


def test_schema_rejects_unknown_fields_in_trial_and_summary() -> None:
    from eval.cross_model_parity import validate_payload_against_schema
    import jsonschema

    trial = {
        "schema_version": "1.0.0",
        "experiment_id": M13_EXPERIMENT_ID,
        "trial_id": "test",
        "order_index": 0,
        "experiment_base_sha": M13_EXPERIMENT_BASE_SHA,
        "execution_base_sha": M13_EXECUTION_BASE_SHA,
        "harness_sha": M13_EXECUTION_BASE_SHA,
        "candidate_id": "llama31_8b_q4km",
        "arm": "control_once",
        "replicate": 1,
        "model_tag": "llama3.1:8b-instruct-q4_K_M",
        "model_family": "llama",
        "model_class": "llama3.1-8b-local",
        "model_digest": FROZEN_CANDIDATES["llama31_8b_q4km"].model_digest,
        "quantization": "Q4_K_M",
        "packaged_context": 131072,
        "effective_context": 32768,
        "tier": "tier_1",
        "task_id": "task_003",
        "task_file": "eval/tasks/003_example.json",
        "task_sha256": "0" * 64,
        "ollama_version": "0.33.2",
        "projected_config_sha256": None,
        "ephemeral_adapter_config_sha256": None,
        "execution_profile_id": None,
        "tool_contract_digest": None,
        "prompt_template_digest": None,
        "runtime_kind": None,
        "runtime_version": None,
        "runtime_model_class": None,
        "execution_base_to_harness_changed_paths": [],
        "generation_call_count": 1,
        "output_paths": [],
        "swarm_enabled": False,
        "recovery_enabled": False,
        "recovery_attempted": False,
        "verifier_completed": True,
        "passed": True,
        "failure_category": None,
        "verifier_payload": None,
        "prompt_tokens": 10,
        "completion_tokens": 10,
        "total_tokens": 20,
        "model_latency_seconds": 0.5,
        "wall_latency_seconds": 0.6,
        "provenance_complete": True,
        "token_coverage_complete": True,
        "infrastructure_error": False,
        "trace_artifact_relpath": None,
        "trace_artifact_sha256": None,
        "raw_response_relpaths": [],
        "raw_response_sha256s": [],
        "timestamp": "2026-09-03T21:00:00Z",
        "unauthorized_field": 123,
    }
    with pytest.raises(jsonschema.ValidationError):
        validate_payload_against_schema(
            trial, "trial_record", DEFAULT_CONTRACT_PATH
        )


def test_production_signal_model_classes_not_mutated(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    import mighty_mouse.v2.records

    expected_controlled = frozenset(
        {"local-small", "local-medium", "local-large", "unknown"}
    )
    # Check baseline matches controlled set
    assert mighty_mouse.v2.records._SIGNAL_MODEL_CLASSES == expected_controlled

    # Run candidate runtime preparation for both models
    with tempfile.TemporaryDirectory() as tmp:
        support_dir = Path(tmp)
        for cand in FROZEN_CANDIDATES.values():
            prepare_candidate_runtime(
                cand, mock_local_context, support_dir / cand.candidate_id
            )

    # Check set remains identical after preparation
    assert mighty_mouse.v2.records._SIGNAL_MODEL_CLASSES == expected_controlled
    assert "llama3.1-8b-local" not in (
        mighty_mouse.v2.records._SIGNAL_MODEL_CLASSES
    )
    assert "qwen2.5-7b-local" not in (
        mighty_mouse.v2.records._SIGNAL_MODEL_CLASSES
    )


def test_unsupported_canonical_runtime_model_class_fails_closed(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    import dataclasses

    bad_ctx = dataclasses.replace(
        mock_local_context, model_class="unsupported-rogue-class"
    )

    cand = FROZEN_CANDIDATES["llama31_8b_q4km"]
    with tempfile.TemporaryDirectory() as tmp:
        with pytest.raises(ValueError, match="not a supported controlled"):
            prepare_candidate_runtime(cand, bad_ctx, Path(tmp))


def test_descriptive_candidate_classes_remain_unchanged() -> None:
    plan = materialize_execution_plan()
    llama_unit = next(
        u for u in plan["trial_units"]
        if u["candidate_id"] == "llama31_8b_q4km"
    )
    qwen_unit = next(
        u for u in plan["trial_units"]
        if u["candidate_id"] == "qwen25_7b_q4km"
    )
    assert llama_unit["model_class"] == "llama3.1-8b-local"
    assert qwen_unit["model_class"] == "qwen2.5-7b-local"


def test_ephemeral_adapters_inherit_canonical_controlled_runtime_model_class(
    mock_local_context: AdapterRuntimeContext,
) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        support_dir = Path(tmp)
        for cand in FROZEN_CANDIDATES.values():
            _, _, a_cfg, _ = prepare_candidate_runtime(
                cand, mock_local_context, support_dir / cand.candidate_id
            )
            data = json.loads(a_cfg.read_text(encoding="utf-8"))
            assert data["model_class"] == mock_local_context.model_class
            assert data["model_class"] in {
                "local-small", "local-medium", "local-large", "unknown"
            }
