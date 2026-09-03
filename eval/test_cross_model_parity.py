"""Tests for eval/cross_model_parity.py and its JSON schema contract."""

from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch
from eval.runner_lock import LOCK_FILE_PATH
import yaml

import jsonschema
import pytest

from eval.cross_model_parity import (
    DEFAULT_CONFIG_PATH,
    DEFAULT_CONTRACT_PATH,
    FROZEN_ANCHOR_TASKS,
    FROZEN_CANDIDATES,
    M13_ALLOWED_ARMS,
    M13_CANONICAL_CONFIG_SHA256,
    M13_EXECUTION_BASE_SHA,
    M13_EXPERIMENT_BASE_SHA,
    M13_HARNESS_ALLOWED_PATHS,
    M13_ORDER_SEED,
    M13_SCHEMA_VERSION,
    compute_sort_hash,
    load_contract_schema,
    materialize_execution_plan,
    project_candidate_config,
    run_preflight,
    validate_execution_plan,
    validate_payload_against_schema,
    verify_base_to_harness_delta,
)


def test_schema_contract_validity() -> None:
    schema = load_contract_schema(DEFAULT_CONTRACT_PATH)
    assert schema["$schema"] == "http://json-schema.org/draft-07/schema#"
    assert schema["version"] == M13_SCHEMA_VERSION
    assert "definitions" in schema
    assert "execution_plan" in schema["definitions"]
    assert "plan_unit" in schema["definitions"]
    assert "preflight_report" in schema["definitions"]


def test_schema_rejects_unknown_top_level_fields() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan_with_extra = dict(plan)
    plan_with_extra["unexpected_field"] = "bad"
    with pytest.raises(jsonschema.ValidationError):
        validate_payload_against_schema(plan_with_extra, "execution_plan")


def test_schema_rejects_unknown_unit_fields() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    bad_unit = dict(plan["trial_units"][0])
    bad_unit["unexpected_extra"] = 123
    with pytest.raises(jsonschema.ValidationError):
        validate_payload_against_schema(bad_unit, "plan_unit")


def test_frozen_candidate_identities() -> None:
    assert len(FROZEN_CANDIDATES) == 2
    llama = FROZEN_CANDIDATES["llama31_8b_q4km"]
    assert llama.candidate_id == "llama31_8b_q4km"
    assert llama.model_tag == "llama3.1:8b-instruct-q4_K_M"
    assert llama.model_family == "llama"
    assert llama.model_class == "llama3.1-8b-local"
    exp_llama = (
        "sha256:667b0c1932bc6ffc593ed1d0"
        "3f895bf2dc8dc6df21db3042284a6f4416b06a29"
    )
    assert llama.model_digest == exp_llama
    assert llama.quantization == "Q4_K_M"
    assert llama.parameter_scale == "8.0B"
    assert llama.packaged_context == 131072
    assert llama.effective_context == 32768

    qwen = FROZEN_CANDIDATES["qwen25_7b_q4km"]
    assert qwen.candidate_id == "qwen25_7b_q4km"
    assert qwen.model_tag == "qwen2.5:7b-instruct-q4_K_M"
    assert qwen.model_family == "qwen2"
    assert qwen.model_class == "qwen2.5-7b-local"
    exp_qwen = (
        "sha256:2bada8a7450677000f678be9"
        "0653b85d364de7db25eb5ea54136ada5f3933730"
    )
    assert qwen.model_digest == exp_qwen
    assert qwen.quantization == "Q4_K_M"
    assert qwen.parameter_scale == "7.6B"
    assert qwen.packaged_context == 32768
    assert qwen.effective_context == 32768


def test_frozen_anchor_tasks_integrity() -> None:
    assert len(FROZEN_ANCHOR_TASKS) == 3
    t1 = FROZEN_ANCHOR_TASKS["task_003"]
    assert t1.tier == "tier_1"
    assert t1.task_id == "task_003"
    assert (
        t1.sha256
        == "d5ac92cf635fb9bb18340df6dc831d6b78fd0ccfaf046e4a79bfcd3657f49976"
    )

    t5 = FROZEN_ANCHOR_TASKS["task_047"]
    assert t5.tier == "tier_5"
    assert t5.task_id == "task_047"
    assert (
        t5.sha256
        == "9e40f53e472658c6689f759b30f20b85b1f9cdcb6d27367115e99e0619b54b47"
    )

    t7 = FROZEN_ANCHOR_TASKS["task_1415"]
    assert t7.tier == "tier_7"
    assert t7.task_id == "task_1415"
    assert (
        t7.sha256
        == "750bec2e8f6f1888fea1dc502d19a123f312f540dbbcfe93dbd5bac39a0db486"
    )

    for task in FROZEN_ANCHOR_TASKS.values():
        p = Path(task.task_file)
        assert p.exists(), f"Task file missing: {task.task_file}"
        actual_sha = hashlib.sha256(p.read_bytes()).hexdigest()
        assert actual_sha == task.sha256


def test_m13_allowed_arms() -> None:
    assert M13_ALLOWED_ARMS == ("control_once", "mm_single")
    assert "mm_swarm" not in M13_ALLOWED_ARMS
    assert "mm_single_recovery" not in M13_ALLOWED_ARMS
    assert "mm_swarm_recovery" not in M13_ALLOWED_ARMS


def test_candidate_config_projection_modifies_only_model() -> None:
    for cand_id, cand in FROZEN_CANDIDATES.items():
        proj_dict, proj_sha = project_candidate_config(cand.model_tag)
        assert proj_dict["model"] == cand.model_tag
        assert proj_dict["temperature"] == 0.2
        assert proj_dict["max_tokens"] == 4000
        assert proj_dict["provider"] == "ollama"

        with open(DEFAULT_CONFIG_PATH, "r", encoding="utf-8") as f:
            canon = yaml.safe_load(f)

        diff_keys = [k for k in proj_dict if proj_dict[k] != canon.get(k)]
        assert diff_keys == ["model"]
        assert len(proj_sha) == 64


def test_project_candidate_config_fails_if_tampered() -> None:
    with patch("eval.cross_model_parity.load_canonical_config") as mock_load:
        mock_load.return_value = {
            "model": "gemma4:e4b",
            "provider": "ollama",
            "temperature": 0.5,
            "max_tokens": 4000,
        }
        with pytest.raises(
            ValueError, match="Canonical configuration parameter tampered"
        ):
            project_candidate_config("llama3.1:8b-instruct-q4_K_M")


def test_materialize_execution_plan_cardinality_and_order() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    assert plan["schema_version"] == M13_SCHEMA_VERSION
    assert plan["experiment_base_sha"] == M13_EXPERIMENT_BASE_SHA
    assert plan["harness_sha"] == M13_EXPERIMENT_BASE_SHA
    assert plan["trial_count"] == 12
    assert len(plan["trial_units"]) == 12

    combos = set()
    sort_hashes = []
    for idx, unit in enumerate(plan["trial_units"]):
        assert unit["order_index"] == idx
        combos.add(
            (
                unit["candidate_id"],
                unit["task_id"],
                unit["arm"],
                unit["replicate"],
            )
        )
        expected_sort_hash = compute_sort_hash(
            M13_EXPERIMENT_BASE_SHA,
            M13_ORDER_SEED,
            unit["candidate_id"],
            unit["task_id"],
            unit["arm"],
            unit["replicate"],
        )
        assert unit["sort_hash"] == expected_sort_hash
        sort_hashes.append(unit["sort_hash"])

        if unit["arm"] == "mm_single":
            assert unit["projected_config_sha256"] is not None
        else:
            assert unit["projected_config_sha256"] is None

    assert len(combos) == 12
    assert sort_hashes == sorted(sort_hashes)


def test_deterministic_materialization_stability() -> None:
    p1 = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    p2 = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    p1_copy = copy.deepcopy(p1)
    p2_copy = copy.deepcopy(p2)
    p1_copy.pop("timestamp")
    p2_copy.pop("timestamp")
    assert p1_copy == p2_copy


def test_validate_execution_plan_valid() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is True
        assert len(report["errors"]) == 0


def test_validate_execution_plan_rejects_altered_base_sha() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["experiment_base_sha"] = "0" * 40
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("experiment_base_sha" in e for e in report["errors"])


def test_validate_execution_plan_rejects_altered_trial_count() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_count"] = 11
    plan["trial_units"] = plan["trial_units"][:11]
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("trial_count" in e for e in report["errors"])


def test_validate_execution_plan_rejects_swarm_arm() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["arm"] = "mm_swarm"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("arm" in e for e in report["errors"])


def test_validate_execution_plan_rejects_recovery_arm() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["arm"] = "mm_single_recovery"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("arm" in e for e in report["errors"])


def test_validate_execution_plan_rejects_swapped_candidate_digest() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["model_digest"] = "sha256:" + "a" * 64
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("digest" in e for e in report["errors"])


def test_validate_execution_plan_rejects_swapped_model_class() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    cur_class = plan["trial_units"][0]["model_class"]
    plan["trial_units"][0]["model_class"] = (
        "llama3.1-8b-local"
        if cur_class == "qwen2.5-7b-local"
        else "qwen2.5-7b-local"
    )
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("model_class" in e for e in report["errors"])


def test_validate_execution_plan_rejects_wrong_quantization() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["quantization"] = "Q8_0"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("quantization" in e for e in report["errors"])


def test_validate_execution_plan_rejects_wrong_effective_context() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["effective_context"] = 16384
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("effective_context" in e for e in report["errors"])


def test_validate_execution_plan_rejects_noncontiguous_order_indices() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][1]["order_index"] = 0
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any("order_index" in e for e in report["errors"])


def test_validate_execution_plan_rejects_wrong_sort_order() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0], plan["trial_units"][1] = (
        plan["trial_units"][1],
        plan["trial_units"][0],
    )
    plan["trial_units"][0]["order_index"] = 0
    plan["trial_units"][1]["order_index"] = 1
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan)
        assert report["valid"] is False
        assert any(
            "sort order" in e or "sort_hash" in e for e in report["errors"]
        )


def test_harness_allowlist_rejects_unauthorized_changes() -> None:
    with patch("subprocess.check_output") as mock_sub:
        mock_sub.return_value = (
            "src/mighty_mouse/orchestrator/mighty_mouse_agent.py\n"
            "eval/cross_model_parity.py\n"
        )
        with pytest.raises(
            ValueError, match="Unauthorized file changes detected"
        ):
            verify_base_to_harness_delta(M13_EXPERIMENT_BASE_SHA, "HEAD")


def test_preflight_passes_without_model_generations() -> None:
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"version": "0.33.2"}'
                mock_resp.__enter__.return_value = mock_resp

                def mock_urlopen(req: Any, *args: Any, **kwargs: Any) -> Any:
                    url = getattr(req, "full_url", str(req))
                    if "/api/generate" in url or "/api/chat" in url:
                        raise RuntimeError(
                            "Inference endpoint invoked during preflight!"
                        )
                    if "/api/version" in url:
                        return mock_resp
                    raise RuntimeError(f"Unexpected url: {url}")

                def mock_digest(model_tag: str) -> str:
                    if "llama" in model_tag:
                        return FROZEN_CANDIDATES[
                            "llama31_8b_q4km"
                        ].model_digest
                    if "qwen" in model_tag:
                        return FROZEN_CANDIDATES[
                            "qwen25_7b_q4km"
                        ].model_digest
                    raise ValueError(f"Unknown model: {model_tag}")

                resolve_fn = (
                    "eval.cross_model_parity.HostAdapter."
                    "resolve_ollama_model_digest"
                )
                with patch("urllib.request.urlopen", side_effect=mock_urlopen):
                    with patch(resolve_fn, side_effect=mock_digest):
                        report = run_preflight()
                        assert report["status"] == "PASSED"
                        assert report["generation_calls"] == 0
                        assert report["mcp_tools_count"] == 15
                        assert report["mcp_contract_version"] == "v6"
                        assert (
                            report["experiment_base_sha"]
                            == M13_EXPERIMENT_BASE_SHA
                        )
                        assert (
                            report["execution_base_sha"]
                            == M13_EXECUTION_BASE_SHA
                        )
                        assert (
                            "execution_base_to_harness_changed_paths" in report
                        )


def test_preflight_fails_on_digest_mismatch() -> None:
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"version": "0.33.2"}'
                mock_resp.__enter__.return_value = mock_resp

                resolve_fn = (
                    "eval.cross_model_parity.HostAdapter."
                    "resolve_ollama_model_digest"
                )
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    with patch(
                        resolve_fn,
                        return_value="sha256:" + "f" * 64,
                    ):
                        report = run_preflight()
                        assert report["status"] == "FAILED"
                        assert any(
                            "digest mismatch" in b.lower()
                            for b in report["blocking_reasons"]
                        )


def test_preflight_fails_on_missing_model() -> None:
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"version": "0.33.2"}'
                mock_resp.__enter__.return_value = mock_resp

                def fail_on_qwen(model_tag: str) -> str:
                    if "qwen" in model_tag:
                        raise RuntimeError(f"model '{model_tag}' not found")
                    return FROZEN_CANDIDATES[
                        "llama31_8b_q4km"
                    ].model_digest

                resolve_fn = (
                    "eval.cross_model_parity.HostAdapter."
                    "resolve_ollama_model_digest"
                )
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    with patch(resolve_fn, side_effect=fail_on_qwen):
                        report = run_preflight()
                        assert report["status"] == "FAILED"
                        assert any(
                            "failed to validate candidate" in b.lower()
                            for b in report["blocking_reasons"]
                        )


def test_preflight_fails_when_ollama_offline() -> None:
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                with patch(
                    "urllib.request.urlopen",
                    side_effect=RuntimeError("Connection refused"),
                ):
                    report = run_preflight()
                    assert report["status"] == "FAILED"
                    assert any(
                        "failed to inspect ollama api" in b.lower()
                        for b in report["blocking_reasons"]
                    )


def test_check_git_clean_except_prototype() -> None:
    from eval.cross_model_parity import check_git_clean_except_prototype

    with patch("subprocess.check_output") as mock_sub:
        mock_sub.return_value = "?? eval/prototype_apple_dashboard.html\n"
        check_git_clean_except_prototype()

        mock_sub.return_value = "?? other_untracked_file.py\n"
        with pytest.raises(ValueError, match="Working tree is not clean"):
            check_git_clean_except_prototype()

        mock_sub.return_value = (
            " M src/mighty_mouse/orchestrator/mighty_mouse_agent.py\n"
        )
        with pytest.raises(ValueError, match="Working tree is not clean"):
            check_git_clean_except_prototype()


def test_preflight_uses_canonical_shared_lock() -> None:
    with patch("eval.cross_model_parity.SingleInstanceLock") as mock_lock:
        mock_ctx = MagicMock()
        mock_lock.return_value.__enter__.return_value = mock_ctx
        with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
            with patch(
                "eval.cross_model_parity.get_current_git_sha",
                return_value=M13_EXPERIMENT_BASE_SHA,
            ):
                with patch(
                    "eval.cross_model_parity.check_git_clean_except_prototype"
                ):
                    with patch(
                        "urllib.request.urlopen",
                        side_effect=RuntimeError("offline"),
                    ):
                        run_preflight()
        mock_lock.assert_called_once_with(LOCK_FILE_PATH)


def test_validate_execution_plan_rejects_stale_harness_sha() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(plan, current_head="1" * 40)
        assert report["valid"] is False
        assert any("harness_sha" in e for e in report["errors"])


def test_validate_plan_rejects_altered_top_level_candidates() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["candidates"]["llama31_8b_q4km"]["parameter_scale"] = "99B"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any("candidates" in e.lower() for e in report["errors"])


def test_validate_plan_rejects_altered_top_level_tasks() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["anchor_tasks"]["task_003"]["tier"] = "tier_99"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any("anchor_tasks" in e.lower() for e in report["errors"])


def test_validate_plan_rejects_altered_canonical_config_sha() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["canonical_config_sha256"] = "f" * 64
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any(
            "canonical_config_sha256" in e.lower() for e in report["errors"]
        )


def test_validate_execution_plan_rejects_wrong_packaged_context() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["packaged_context"] = 99999
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any("packaged_context" in e.lower() for e in report["errors"])


def test_validate_execution_plan_rejects_swapped_tier() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["tier"] = "tier_99"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any("tier" in e.lower() for e in report["errors"])


def test_validate_execution_plan_rejects_wrong_task_file() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["task_file"] = "tasks/benchmark/wrong_task.json"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any("task_file" in e.lower() for e in report["errors"])


def test_validate_execution_plan_rejects_wrong_projected_config_sha() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    for u in plan["trial_units"]:
        if u["arm"] == "mm_single":
            u["projected_config_sha256"] = "f" * 64
            break
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any(
            "projected_config_sha256" in e.lower() for e in report["errors"]
        )


def test_validate_plan_rejects_non_null_control_projected_sha() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    for u in plan["trial_units"]:
        if u["arm"] == "control_once":
            u["projected_config_sha256"] = "f" * 64
            break
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any(
            "projected_config_sha256" in e.lower() for e in report["errors"]
        )


def test_validate_execution_plan_rejects_arbitrary_trial_id() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["trial_units"][0]["trial_id"] = "arbitrary_custom_id_123"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any("trial_id" in e.lower() for e in report["errors"])


def test_preflight_returns_schema_valid_failed_report_on_tampered_config(
    tmp_path: Path,
) -> None:
    bad_cfg = tmp_path / "bad_config.yaml"
    bad_cfg.write_text("provider: openai\nmodel: gpt-4\n", encoding="utf-8")
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                report = run_preflight(config_path=bad_cfg)
                assert report["status"] == "FAILED"
                assert report["generation_calls"] == 0
                assert any(
                    "config" in b.lower() for b in report["blocking_reasons"]
                )
                validate_payload_against_schema(report, "preflight_report")


def test_preflight_fails_on_mcp_tool_count_mismatch() -> None:
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"version": "0.33.2"}'
                mock_resp.__enter__.return_value = mock_resp

                def mock_digest(tag: str) -> str:
                    if "llama" in tag:
                        return FROZEN_CANDIDATES[
                            "llama31_8b_q4km"
                        ].model_digest
                    return FROZEN_CANDIDATES["qwen25_7b_q4km"].model_digest

                resolve_fn = (
                    "eval.cross_model_parity.HostAdapter."
                    "resolve_ollama_model_digest"
                )
                sig_fn = "mighty_mouse_mcp.server._get_mcp_tool_signatures"
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    with patch(resolve_fn, side_effect=mock_digest):
                        with patch(sig_fn, return_value={"tool1": None}):
                            report = run_preflight()
                            assert report["status"] == "FAILED"
                            assert report["mcp_tools_count"] == 1
                            assert any(
                                "mcp tool count mismatch" in b.lower()
                                for b in report["blocking_reasons"]
                            )
                            validate_payload_against_schema(
                                report, "preflight_report"
                            )


def test_preflight_fails_on_mcp_contract_version_mismatch() -> None:
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"version": "0.33.2"}'
                mock_resp.__enter__.return_value = mock_resp

                def mock_digest(tag: str) -> str:
                    if "llama" in tag:
                        return FROZEN_CANDIDATES[
                            "llama31_8b_q4km"
                        ].model_digest
                    return FROZEN_CANDIDATES["qwen25_7b_q4km"].model_digest

                resolve_fn = (
                    "eval.cross_model_parity.HostAdapter."
                    "resolve_ollama_model_digest"
                )
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    with patch(resolve_fn, side_effect=mock_digest):
                        ver_target = (
                            "eval.cross_model_parity."
                            "MCP_TOOL_CONTRACT_VERSION"
                        )
                        with patch(ver_target, 99):
                            report = run_preflight()
                            assert report["status"] == "FAILED"
                            assert report["mcp_contract_version"] == "v99"
                            assert any(
                                "mcp contract version mismatch" in b.lower()
                                for b in report["blocking_reasons"]
                            )
                            validate_payload_against_schema(
                                report, "preflight_report"
                            )


def test_plan_survives_json_roundtrip() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    serialized = json.dumps(plan)
    reloaded = json.loads(serialized)
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            reloaded, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is True, f"Errors: {report['errors']}"
        assert reloaded == plan


def test_validate_plan_rejects_altered_experiment_id() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["experiment_id"] = "tampered_id"
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any("experiment_id" in e for e in report["errors"])


def test_validate_plan_rejects_non_canonical_cfg_path(
    tmp_path: Path,
) -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    # Even if byte-identical, path must be configs/mighty_mouse_v1.yaml
    alt_cfg = tmp_path / "mighty_mouse_v1.yaml"
    alt_cfg.write_bytes(DEFAULT_CONFIG_PATH.read_bytes())
    plan["canonical_config_path"] = str(alt_cfg)
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any("canonical_config_path" in e for e in report["errors"])


def test_preflight_uses_mcp_signature_map() -> None:
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"version": "0.33.2"}'
                mock_resp.__enter__.return_value = mock_resp

                def mock_digest(tag: str) -> str:
                    if "llama" in tag:
                        return FROZEN_CANDIDATES[
                            "llama31_8b_q4km"
                        ].model_digest
                    return FROZEN_CANDIDATES["qwen25_7b_q4km"].model_digest

                resolve_fn = (
                    "eval.cross_model_parity.HostAdapter."
                    "resolve_ollama_model_digest"
                )
                sig_fn = "mighty_mouse_mcp.server._get_mcp_tool_signatures"
                two_tools = {"t1": None, "t2": None}
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    with patch(resolve_fn, side_effect=mock_digest):
                        with patch(sig_fn, return_value=two_tools) as mock_sig:
                            report = run_preflight()
                            mock_sig.assert_called_once()
                            assert report["status"] == "FAILED"
                            assert report["mcp_tools_count"] == 2
                            assert any(
                                "mcp tool count mismatch" in b.lower()
                                for b in report["blocking_reasons"]
                            )


def test_preflight_fails_on_mcp_signature_inspection_error() -> None:
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.get_current_git_sha",
            return_value=M13_EXPERIMENT_BASE_SHA,
        ):
            with patch(
                "eval.cross_model_parity.check_git_clean_except_prototype"
            ):
                mock_resp = MagicMock()
                mock_resp.read.return_value = b'{"version": "0.33.2"}'
                mock_resp.__enter__.return_value = mock_resp

                def mock_digest(tag: str) -> str:
                    if "llama" in tag:
                        return FROZEN_CANDIDATES[
                            "llama31_8b_q4km"
                        ].model_digest
                    return FROZEN_CANDIDATES["qwen25_7b_q4km"].model_digest

                resolve_fn = (
                    "eval.cross_model_parity.HostAdapter."
                    "resolve_ollama_model_digest"
                )
                sig_fn = "mighty_mouse_mcp.server._get_mcp_tool_signatures"
                mcp_err = RuntimeError("MCP import error")
                with patch("urllib.request.urlopen", return_value=mock_resp):
                    with patch(resolve_fn, side_effect=mock_digest):
                        with patch(sig_fn, side_effect=mcp_err):
                            report = run_preflight()
                            assert report["status"] == "FAILED"
                            assert report["mcp_tools_count"] is None
                            assert any(
                                "failed to inspect mcp" in b.lower()
                                for b in report["blocking_reasons"]
                            )
                            validate_payload_against_schema(
                                report, "preflight_report"
                            )


def test_validate_plan_fails_closed_on_projection_exception() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        with patch(
            "eval.cross_model_parity.project_candidate_config",
            side_effect=RuntimeError("Syntax error in config"),
        ):
            report = validate_execution_plan(
                plan, current_head=M13_EXPERIMENT_BASE_SHA
            )
            assert report["valid"] is False
            assert any(
                "projection failed" in e.lower() for e in report["errors"]
            )


def test_validate_plan_rejects_altered_canonical_config_sha_constant() -> None:
    plan = materialize_execution_plan(harness_sha=M13_EXPERIMENT_BASE_SHA)
    plan["canonical_config_sha256"] = "0" * 64
    with patch("eval.cross_model_parity.verify_base_to_harness_delta"):
        report = validate_execution_plan(
            plan, current_head=M13_EXPERIMENT_BASE_SHA
        )
        assert report["valid"] is False
        assert any(
            "canonical_config_sha256" in e.lower() for e in report["errors"]
        )


def test_canonical_config_file_hash_matches_frozen_constant() -> None:
    actual = hashlib.sha256(DEFAULT_CONFIG_PATH.read_bytes()).hexdigest()
    assert actual == M13_CANONICAL_CONFIG_SHA256


def test_harness_allowlist_contains_exactly_five_m13_files() -> None:
    expected = {
        "eval/cross_model_parity.py",
        "eval/cross_model_parity_contract.json",
        "eval/test_cross_model_parity.py",
        "eval/cross_model_parity_execution.py",
        "eval/test_cross_model_parity_execution.py",
    }
    assert M13_HARNESS_ALLOWED_PATHS == expected


def test_verify_base_to_harness_delta_defaults_to_execution_base() -> None:
    with patch(
        "subprocess.check_output",
        return_value="eval/cross_model_parity.py\n",
    ) as mock_co:
        paths = verify_base_to_harness_delta(
            harness_sha=M13_EXECUTION_BASE_SHA
        )
        assert paths == ["eval/cross_model_parity.py"]
        mock_co.assert_called_once_with(
            [
                "git",
                "diff",
                "--name-only",
                f"{M13_EXECUTION_BASE_SHA}..{M13_EXECUTION_BASE_SHA}",
            ],
            text=True,
        )
