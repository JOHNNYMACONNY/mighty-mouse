"""Tests for ComputeScalingPolicy and dynamic compute scaling MCP tools."""

from pathlib import Path
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
