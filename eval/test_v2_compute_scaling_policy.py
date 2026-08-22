"""Tests for ComputeScalingPolicy and dynamic compute scaling MCP tools."""

import json
from pathlib import Path
from typing import Any
import pytest

from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.foundation import (
    ComputeScalingPin,
    ComputeScalingPolicy,
    ExecutionProfile,
    ImmutableStateStore,
    Mode,
    ModelIdentity,
    Scope,
    TaskCategory,
)
from mighty_mouse_mcp.server import (
    _get_mcp_tool_signatures,
    run_compute_scaling_pin,
    run_compute_scaling_preview,
    run_compute_scaling_status,
    run_setup_workspace,
)


def _setup_workspace_adapter(workspace: Path) -> None:
    run_setup_workspace(
        str(workspace),
        "JOHNNYMACONNY/mighty-mouse",
        model_digest="sha256:" + "a" * 64,
        model_class="local-small",
        runtime_kind="antigravity",
        runtime_version="2.0.0",
    )


def test_compute_scaling_policy_defaults_and_immutability():
    policy = ComputeScalingPolicy()
    assert policy.variations == 3
    assert policy.temperature_schedule == (0.0, 0.35, 0.70)
    assert policy.consensus_strategy == "min_diff"
    assert policy.feedback_loop_enabled is True

    custom = ComputeScalingPolicy(
        variations=5,
        temperature_schedule=(0.1, 0.5),
        consensus_strategy="unanimous",
        feedback_loop_enabled=False,
    )
    assert custom.variations == 5
    assert custom.temperature_schedule == (0.1, 0.5)
    assert custom.consensus_strategy == "unanimous"
    assert custom.feedback_loop_enabled is False

    with pytest.raises(Exception):
        custom.variations = 10  # type: ignore[misc]


def test_compute_scaling_pin_state_store_roundtrip(tmp_path: Path):
    store = ImmutableStateStore(tmp_path)
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    scaling_policy = ComputeScalingPolicy(
        variations=4, temperature_schedule=(0.0, 0.5)
    )
    pin = ComputeScalingPin(
        pin_id="cspin-123456",
        scope=scope,
        scaling_policy=scaling_policy,
        model_digest="sha256:" + "a" * 64,
        execution_profile_id="sha256:" + "b" * 64,
    )

    record = store.append(pin)
    assert record.record_hash is not None

    reloaded_store = ImmutableStateStore(tmp_path)
    records = reloaded_store.records()
    assert len(records) == 1
    reloaded_pin = records[0].value
    assert isinstance(reloaded_pin, ComputeScalingPin)
    assert reloaded_pin.pin_id == "cspin-123456"
    assert reloaded_pin.scaling_policy.variations == 4
    assert reloaded_pin.scaling_policy.temperature_schedule == (0.0, 0.5)


def test_compute_scaling_pin_deserialization_from_raw_json():
    # Test deserialization of raw JSON document matching on-disk state
    raw_value = {
        "pin_id": "cspin-legacy-001",
        "scope": {
            "mode": "coding",
            "repository": "JOHNNYMACONNY/mighty-mouse",
            "task_category": "feature",
            "model_class": "local-small",
        },
        "scaling_policy": {
            "variations": 3,
            "temperature_schedule": [0.0, 0.35, 0.70],
            "consensus_strategy": "min_diff",
            "feedback_loop_enabled": True,
        },
        "model_digest": "sha256:" + "a" * 64,
        "execution_profile_id": "sha256:" + "b" * 64,
    }
    from mighty_mouse.v2.records import _record_from_value

    pin = _record_from_value("compute_scaling_pin", raw_value)
    assert isinstance(pin, ComputeScalingPin)
    assert pin.pin_id == "cspin-legacy-001"
    assert pin.scaling_policy.variations == 3
    assert pin.scaling_policy.temperature_schedule == (0.0, 0.35, 0.70)
    assert pin.scaling_policy.consensus_strategy == "min_diff"
    assert pin.scaling_policy.feedback_loop_enabled is True


def test_policy_engine_scaling_status_and_pin(tmp_path: Path):
    engine = PolicyEngine(tmp_path)
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_id = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("sha256:" + "b" * 64, frozenset({"test"}))

    # Before pin: returns defaults
    status_default = engine.get_scaling_status(scope, model_id, profile)
    assert status_default["is_pinned"] is False
    assert status_default["pin_id"] is None
    assert status_default["scaling_policy"]["variations"] == 3

    # Pin custom scaling policy
    custom_policy = ComputeScalingPolicy(
        variations=6,
        temperature_schedule=(0.0, 0.2, 0.4, 0.6, 0.8, 1.0),
    )
    pin = ComputeScalingPin(
        pin_id="cspin-custom-001",
        scope=scope,
        scaling_policy=custom_policy,
        model_digest=model_id.artifact_digest,
        execution_profile_id=profile.profile_id,
    )
    engine.pin_scaling(pin, model_id, profile)

    # After pin: returns custom pinned configuration
    status_pinned = engine.get_scaling_status(scope, model_id, profile)
    assert status_pinned["is_pinned"] is True
    assert status_pinned["pin_id"] == "cspin-custom-001"
    assert status_pinned["scaling_policy"]["variations"] == 6


def test_mcp_compute_scaling_tools_end_to_end(tmp_path: Path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    _setup_workspace_adapter(workspace)

    # 1. Preview
    preview_res = run_compute_scaling_preview(
        str(workspace),
        variations=5,
        temperature_schedule=[0.0, 0.25, 0.5, 0.75, 1.0],
        consensus_strategy="min_diff",
        feedback_loop_enabled=True,
    )
    assert preview_res["interface"] == "compute_scaling_preview"
    assert preview_res["preview_scaling_policy"]["variations"] == 5
    assert (
        len(preview_res["preview_scaling_policy"]["temperature_schedule"]) == 5
    )

    # 2. Status before pin
    status_before = run_compute_scaling_status(str(workspace))
    assert status_before["interface"] == "compute_scaling_status"
    assert status_before["is_pinned"] is False
    assert status_before["scaling_policy"]["variations"] == 3

    # 3. Pin
    pin_res = run_compute_scaling_pin(
        str(workspace),
        variations=5,
        temperature_schedule=[0.0, 0.25, 0.5, 0.75, 1.0],
        consensus_strategy="min_diff",
        feedback_loop_enabled=True,
    )
    assert pin_res["interface"] == "compute_scaling_pin"
    assert pin_res["scaling_policy"]["variations"] == 5
    assert "pin_id" in pin_res

    # 4. Status after pin
    status_after = run_compute_scaling_status(str(workspace))
    assert status_after["is_pinned"] is True
    assert status_after["pin_id"] == pin_res["pin_id"]
    assert status_after["scaling_policy"]["variations"] == 5


def test_mcp_tool_signatures_includes_scaling_tools():
    sigs = _get_mcp_tool_signatures()
    assert "compute_scaling_status" in sigs
    assert "compute_scaling_preview" in sigs
    assert "compute_scaling_pin" in sigs
    assert len(sigs) == 13


def test_compute_scaling_policy_variations_bounds_and_types():
    # Valid variation boundaries
    p1 = ComputeScalingPolicy(variations=1, temperature_schedule=(0.5,))
    assert p1.variations == 1
    p8 = ComputeScalingPolicy(variations=8, temperature_schedule=(0.0, 0.5))
    assert p8.variations == 8

    # Invalid values
    with pytest.raises(ValueError, match="between 1 and 8"):
        ComputeScalingPolicy(variations=0)
    with pytest.raises(ValueError, match="between 1 and 8"):
        ComputeScalingPolicy(variations=9)
    with pytest.raises(ValueError, match="integer, not bool"):
        ComputeScalingPolicy(variations=True)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="integer, not bool"):
        ComputeScalingPolicy(variations=False)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="integer, not bool"):
        ComputeScalingPolicy(variations="3")  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="integer, not bool"):
        ComputeScalingPolicy(variations=3.5)  # type: ignore[arg-type]


def test_compute_scaling_policy_temperature_schedule_validation():
    # Empty schedule
    with pytest.raises(ValueError, match="at least one value"):
        ComputeScalingPolicy(variations=3, temperature_schedule=())

    # Schedule longer than variations
    with pytest.raises(ValueError, match="cannot exceed variations"):
        ComputeScalingPolicy(
            variations=2, temperature_schedule=(0.1, 0.2, 0.3)
        )

    # Out-of-range temperatures
    with pytest.raises(ValueError, match="between 0.0 and 2.0"):
        ComputeScalingPolicy(variations=2, temperature_schedule=(-0.1,))
    with pytest.raises(ValueError, match="between 0.0 and 2.0"):
        ComputeScalingPolicy(variations=2, temperature_schedule=(2.1,))

    # Non-finite values
    with pytest.raises(ValueError, match="finite numbers"):
        ComputeScalingPolicy(
            variations=2, temperature_schedule=(float("nan"),)
        )
    with pytest.raises(ValueError, match="finite numbers"):
        ComputeScalingPolicy(
            variations=2, temperature_schedule=(float("inf"),)
        )

    # Boolean temperature values
    with pytest.raises(ValueError, match="numeric, not bool"):
        ComputeScalingPolicy(
            variations=2,
            temperature_schedule=(True, 0.5),  # type: ignore[arg-type]
        )

    # Non-sequence schedule
    with pytest.raises(ValueError, match="sequence of numbers"):
        ComputeScalingPolicy(
            variations=2, temperature_schedule=123  # type: ignore[arg-type]
        )


def test_compute_scaling_policy_consensus_strategy_validation():
    # Valid strategies
    p_min = ComputeScalingPolicy(consensus_strategy="min_diff")
    assert p_min.consensus_strategy == "min_diff"
    p_unan = ComputeScalingPolicy(consensus_strategy="unanimous")
    assert p_unan.consensus_strategy == "unanimous"

    # Invalid strategy
    with pytest.raises(ValueError, match="unknown consensus strategy"):
        ComputeScalingPolicy(consensus_strategy="majority")
    with pytest.raises(ValueError, match="unknown consensus strategy"):
        ComputeScalingPolicy(consensus_strategy="")


def test_compute_scaling_policy_feedback_loop_enabled_validation():
    p_true = ComputeScalingPolicy(feedback_loop_enabled=True)
    assert p_true.feedback_loop_enabled is True
    p_false = ComputeScalingPolicy(feedback_loop_enabled=False)
    assert p_false.feedback_loop_enabled is False

    with pytest.raises(ValueError, match="must be a bool"):
        ComputeScalingPolicy(feedback_loop_enabled=1)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="must be a bool"):
        ComputeScalingPolicy(
            feedback_loop_enabled="true"  # type: ignore[arg-type]
        )


def test_compute_scaling_policy_effective_schedule_expansion():
    # Exact length matches variations
    p3 = ComputeScalingPolicy(
        variations=3, temperature_schedule=(0.0, 0.35, 0.70)
    )
    assert p3.effective_temperature_schedule() == (0.0, 0.35, 0.70)

    # Shorter schedule repeats final temperature
    p5 = ComputeScalingPolicy(variations=5, temperature_schedule=(0.1, 0.5))
    assert p5.effective_temperature_schedule() == (
        0.1,
        0.5,
        0.5,
        0.5,
        0.5,
    )

    # Single temperature repeats for all variations
    p4_single = ComputeScalingPolicy(variations=4, temperature_schedule=(0.2,))
    assert p4_single.effective_temperature_schedule() == (0.2, 0.2, 0.2, 0.2)


def test_policy_engine_resolve_scaling_policy_canonical(tmp_path: Path):
    engine = PolicyEngine(tmp_path)
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    other_scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/other-repo",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_id = ModelIdentity("sha256:" + "a" * 64)
    incomplete_model_id = ModelIdentity(None)
    other_model_id = ModelIdentity("sha256:" + "c" * 64)

    profile = ExecutionProfile("sha256:" + "b" * 64, frozenset({"test"}))
    incomplete_profile = ExecutionProfile("", frozenset({"test"}))
    other_profile = ExecutionProfile("sha256:" + "d" * 64, frozenset({"test"}))

    # 1. Unpinned: returns None
    assert engine.resolve_scaling_policy(scope, model_id, profile) is None

    # Pin custom scaling policy
    custom_policy = ComputeScalingPolicy(
        variations=4, temperature_schedule=(0.0, 0.5)
    )
    pin = ComputeScalingPin(
        pin_id="cspin-123456",
        scope=scope,
        scaling_policy=custom_policy,
        model_digest=model_id.artifact_digest,
        execution_profile_id=profile.profile_id,
    )
    engine.pin_scaling(pin, model_id, profile)

    # 2. Pinned exact match: returns pinned ComputeScalingPolicy
    resolved = engine.resolve_scaling_policy(scope, model_id, profile)
    assert resolved == custom_policy

    # 2b. Canonical pin resolution returns exact ComputeScalingPin
    resolved_pin = engine.resolve_scaling_pin(scope, model_id, profile)
    assert resolved_pin == pin
    assert resolved_pin.pin_id == "cspin-123456"
    assert resolved_pin.scaling_policy == custom_policy

    # 3. Incomplete model identity: returns None
    assert (
        engine.resolve_scaling_policy(
            scope, incomplete_model_id, profile
        )
        is None
    )
    assert (
        engine.resolve_scaling_pin(
            scope, incomplete_model_id, profile
        )
        is None
    )

    # 4. Incomplete execution profile: returns None
    assert (
        engine.resolve_scaling_policy(scope, model_id, incomplete_profile)
        is None
    )
    assert (
        engine.resolve_scaling_pin(scope, model_id, incomplete_profile)
        is None
    )

    # 5. Scope mismatch: returns None
    assert (
        engine.resolve_scaling_policy(other_scope, model_id, profile) is None
    )
    assert (
        engine.resolve_scaling_pin(other_scope, model_id, profile) is None
    )

    # 6. Model digest mismatch: returns None
    assert (
        engine.resolve_scaling_policy(scope, other_model_id, profile) is None
    )
    assert (
        engine.resolve_scaling_pin(scope, other_model_id, profile) is None
    )

    # 7. Execution profile ID mismatch: returns None
    assert (
        engine.resolve_scaling_policy(scope, model_id, other_profile) is None
    )
    assert (
        engine.resolve_scaling_pin(scope, model_id, other_profile) is None
    )


def test_policy_engine_pin_scaling_provenance_checks(tmp_path: Path):
    engine = PolicyEngine(tmp_path)
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_id = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("sha256:" + "b" * 64, frozenset({"test"}))
    policy = ComputeScalingPolicy(
        variations=2, temperature_schedule=(0.1, 0.2)
    )

    # Incomplete model identity rejected
    pin_bad_model = ComputeScalingPin(
        pin_id="cspin-1",
        scope=scope,
        scaling_policy=policy,
        model_digest="sha256:" + "a" * 64,
        execution_profile_id="sha256:" + "b" * 64,
    )
    with pytest.raises(ValueError, match="Incomplete model identity"):
        engine.pin_scaling(
            pin_bad_model, ModelIdentity(None), profile
        )

    # Mismatched model digest rejected
    with pytest.raises(ValueError, match="model digest does not match"):
        engine.pin_scaling(
            pin_bad_model,
            ModelIdentity("sha256:" + "z" * 64),
            profile,
        )

    # Mismatched execution profile ID rejected
    with pytest.raises(
        ValueError, match="execution profile ID does not match"
    ):
        engine.pin_scaling(
            pin_bad_model,
            model_id,
            ExecutionProfile(
                "sha256:" + "z" * 64, frozenset({"test"})
            ),
        )


def test_immutable_state_store_compute_scaling_pin_malformed_rejection(
    tmp_path: Path,
):
    def _write_state_doc(dir_path: Path, value_doc: dict[str, Any]) -> None:
        from hashlib import sha256
        dir_path.mkdir(parents=True, exist_ok=True)
        doc = {
            "schema_version": 2,
            "record_type": "compute_scaling_pin",
            "previous_record_hash": None,
            "recorded_at": "2026-08-21T00:00:00+00:00",
            "value": value_doc,
        }
        doc["record_hash"] = sha256(
            json.dumps(doc, sort_keys=True, separators=(",", ":")).encode(
                "utf-8"
            )
        ).hexdigest()
        (dir_path / "v2-state.jsonl").write_text(
            json.dumps(doc) + "\n", encoding="utf-8"
        )

    base_value = {
        "pin_id": "cspin-test-001",
        "scope": {
            "mode": "coding",
            "repository": "JOHNNYMACONNY/mighty-mouse",
            "task_category": "feature",
            "model_class": "local-small",
        },
        "scaling_policy": {
            "variations": 3,
            "temperature_schedule": [0.0, 0.35, 0.70],
            "consensus_strategy": "min_diff",
            "feedback_loop_enabled": True,
        },
        "model_digest": "sha256:" + "a" * 64,
        "execution_profile_id": "sha256:" + "b" * 64,
    }

    # Case 1: variations=True
    bad_var_bool = json.loads(json.dumps(base_value))
    bad_var_bool["scaling_policy"]["variations"] = True
    d1 = tmp_path / "d1"
    _write_state_doc(d1, bad_var_bool)
    with pytest.raises(ValueError, match="integer, not bool"):
        ImmutableStateStore(d1).records()

    # Case 2: variations="3"
    bad_var_str = json.loads(json.dumps(base_value))
    bad_var_str["scaling_policy"]["variations"] = "3"
    d2 = tmp_path / "d2"
    _write_state_doc(d2, bad_var_str)
    with pytest.raises(ValueError, match="integer, not bool"):
        ImmutableStateStore(d2).records()

    # Case 3: temperature=True
    bad_temp_bool = json.loads(json.dumps(base_value))
    bad_temp_bool["scaling_policy"]["temperature_schedule"] = [True]
    d3 = tmp_path / "d3"
    _write_state_doc(d3, bad_temp_bool)
    with pytest.raises(ValueError, match="numeric, not bool"):
        ImmutableStateStore(d3).records()

    # Case 4: temperature="0.5"
    bad_temp_str = json.loads(json.dumps(base_value))
    bad_temp_str["scaling_policy"]["temperature_schedule"] = ["0.5"]
    d4 = tmp_path / "d4"
    _write_state_doc(d4, bad_temp_str)
    with pytest.raises(ValueError, match="numeric, not bool"):
        ImmutableStateStore(d4).records()

    # Case 5: feedback_loop_enabled="false"
    bad_fb_str = json.loads(json.dumps(base_value))
    bad_fb_str["scaling_policy"]["feedback_loop_enabled"] = "false"
    d5 = tmp_path / "d5"
    _write_state_doc(d5, bad_fb_str)
    with pytest.raises(ValueError, match="must be a bool"):
        ImmutableStateStore(d5).records()

    # Case 6: unknown consensus strategy
    bad_strat = json.loads(json.dumps(base_value))
    bad_strat["scaling_policy"]["consensus_strategy"] = "invalid_strat"
    d6 = tmp_path / "d6"
    _write_state_doc(d6, bad_strat)
    with pytest.raises(ValueError, match="unknown consensus strategy"):
        ImmutableStateStore(d6).records()

    # Case 7: Valid ComputeScalingPin survives real state store round-trip
    d7 = tmp_path / "d7"
    d7.mkdir()
    store = ImmutableStateStore(d7)
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    pin = ComputeScalingPin(
        pin_id="cspin-valid-roundtrip",
        scope=scope,
        scaling_policy=ComputeScalingPolicy(
            variations=4, temperature_schedule=(0.0, 0.5)
        ),
        model_digest="sha256:" + "a" * 64,
        execution_profile_id="sha256:" + "b" * 64,
    )
    store.append(pin)
    reloaded = ImmutableStateStore(d7).records()
    assert len(reloaded) == 1
    assert reloaded[0].value == pin
