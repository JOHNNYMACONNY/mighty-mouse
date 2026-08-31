"""Tests for Host Hook Recovery Gate v1 (pure/non-mutating)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
from typing import Any
from unittest.mock import patch
import pytest

from mighty_mouse.host.adapter import (
    AdapterRuntimeContext,
    ExecutionProfile,
    HostAdapter,
    ModelIdentity,
)
from mighty_mouse.host.hooks import (
    HookVerificationSummary,
    HostHookAction,
    HostHookEvent,
    ResolvedHostHookEvent,
)
from mighty_mouse.host.recovery import (
    HookRecoveryDecision,
    evaluate_recovery_gate,
)


def _make_dummy_context(
    state_dir: str = "/fake/workspace/.mighty-mouse",
) -> AdapterRuntimeContext:
    profile = ExecutionProfile(
        profile_id="prof-123",
        runtime_kind="antigravity",
        runtime_version="1.0.0",
        effective_context_limit=32000,
        tool_contract_digest="sha256:abc",
        prompt_template_digest="sha256:def",
        sampling_settings={},
        resource_limits={},
        capabilities=frozenset({"mcp"}),
    )
    return AdapterRuntimeContext(
        state_dir=Path(state_dir),
        repository="test-org/test-repo",
        model_class="gemma-27b",
        model_identity=ModelIdentity(artifact_digest="sha256:111"),
        execution_profile=profile,
        model_source="host",
    )


def _make_resolved_event(
    *,
    kind: str = "file_write",
    mutation_class: str = "workspace_mutation",
    phase: str = "post_action",
    workspace: str = "/fake/workspace",
) -> ResolvedHostHookEvent:
    action = HostHookAction(
        kind=kind,  # type: ignore[arg-type]
        mutation_class=mutation_class,  # type: ignore[arg-type]
        target_paths=("src/main.py",),
    )
    event = HostHookEvent(
        schema_version=1,
        event_id="evt-123",
        phase=phase,  # type: ignore[arg-type]
        workspace=workspace,
        action=action,
        source="antigravity",
    )
    return ResolvedHostHookEvent(
        event=event,
        runtime_context=_make_dummy_context(f"{workspace}/.mighty-mouse"),
    )


def test_hook_recovery_decision_frozen() -> None:
    """HookRecoveryDecision must be a frozen dataclass."""
    dec = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="Recovery eligible",
        execution_mode="agent",
    )
    with pytest.raises(FrozenInstanceError):
        dec.eligible = False  # type: ignore[misc]


def test_hook_recovery_decision_invariants() -> None:
    """HookRecoveryDecision enforces strict internal validation."""
    with pytest.raises(ValueError, match="eligible must be a boolean"):
        HookRecoveryDecision(
            eligible="true",  # type: ignore[arg-type]
            gate_reason="eligible",
            summary="test",
            execution_mode="agent",
        )

    with pytest.raises(ValueError, match="gate_reason must be a non-empty"):
        HookRecoveryDecision(
            eligible=True,
            gate_reason="",
            summary="test",
            execution_mode="agent",
        )

    with pytest.raises(ValueError, match="execution_mode must be 'agent'"):
        HookRecoveryDecision(
            eligible=True,
            gate_reason="eligible",
            summary="test",
            execution_mode=None,
        )

    with pytest.raises(ValueError, match="execution_mode must be 'agent'"):
        HookRecoveryDecision(
            eligible=True,
            gate_reason="eligible",
            summary="test",
            execution_mode="swarm",
        )

    with pytest.raises(ValueError, match="execution_mode must be 'agent'"):
        HookRecoveryDecision(
            eligible=True,
            gate_reason="eligible",
            summary="test",
            execution_mode="invalid_mode",  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="execution_mode must be None"):
        HookRecoveryDecision(
            eligible=False,
            gate_reason="not_applicable",
            summary="test",
            execution_mode="agent",
        )


def test_recovery_eligible_when_all_conditions_satisfied() -> None:
    """Eligible on failed verification, write, enabled, not recursive, 0."""
    resolved = _make_resolved_event(
        kind="file_write", mutation_class="workspace_mutation"
    )
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
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


def test_recovery_not_applicable_when_verification_indeterminate() -> None:
    """occurred=True, passed=None (indeterminate) -> not_applicable."""
    resolved = _make_resolved_event()
    verif = HookVerificationSummary(
        occurred=True, passed=None, summary="Verification indeterminate"
    )
    decision = evaluate_recovery_gate(
        resolved,
        verif,
        enabled=True,
        attempts_used=0,
        recovery_in_progress=False,
    )
    assert decision.eligible is False
    assert decision.gate_reason == "not_applicable"
    assert decision.execution_mode is None


def test_recovery_not_applicable_when_verification_absent() -> None:
    """Verification is None -> not_applicable."""
    resolved = _make_resolved_event()
    decision = evaluate_recovery_gate(
        resolved,
        None,
        enabled=True,
        attempts_used=0,
        recovery_in_progress=False,
    )
    assert decision.eligible is False
    assert decision.gate_reason == "not_applicable"
    assert decision.execution_mode is None


def test_recovery_not_applicable_when_verification_not_occurred() -> None:
    """Verification did not occur -> not_applicable."""
    resolved = _make_resolved_event()
    verif = HookVerificationSummary(
        occurred=False, passed=None, summary="Verification not run"
    )
    decision = evaluate_recovery_gate(
        resolved,
        verif,
        enabled=True,
        attempts_used=0,
        recovery_in_progress=False,
    )
    assert decision.eligible is False
    assert decision.gate_reason == "not_applicable"
    assert decision.execution_mode is None


def test_recovery_not_applicable_when_verification_passed() -> None:
    """Verification passed -> not_applicable (no recovery needed)."""
    resolved = _make_resolved_event()
    verif = HookVerificationSummary(
        occurred=True, passed=True, summary="Verification passed"
    )
    decision = evaluate_recovery_gate(
        resolved,
        verif,
        enabled=True,
        attempts_used=0,
        recovery_in_progress=False,
    )
    assert decision.eligible is False
    assert decision.gate_reason == "not_applicable"
    assert decision.execution_mode is None


@pytest.mark.parametrize(
    ("kind", "mut_class"),
    [
        ("shell_command", "workspace_mutation"),
        ("shell_command", "read_only"),
        ("other", "workspace_mutation"),
        ("file_delete", "workspace_mutation"),
        ("file_write", "read_only"),
        ("file_write", "repository_mutation"),
        ("file_write", "unknown"),
    ],
)
def test_recovery_not_applicable_for_ineligible_action_or_mutation(
    kind: str, mut_class: str
) -> None:
    """Actions other than file_write + workspace_mutation -> not_applicable."""
    resolved = _make_resolved_event(kind=kind, mutation_class=mut_class)
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
    )
    decision = evaluate_recovery_gate(
        resolved,
        verif,
        enabled=True,
        attempts_used=0,
        recovery_in_progress=False,
    )
    assert decision.eligible is False
    assert decision.gate_reason == "not_applicable"
    assert decision.execution_mode is None


def test_recovery_not_enabled() -> None:
    """Failed verification but enabled=False -> recovery_not_enabled."""
    resolved = _make_resolved_event()
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
    )
    decision = evaluate_recovery_gate(
        resolved,
        verif,
        enabled=False,
        attempts_used=0,
        recovery_in_progress=False,
    )
    assert decision.eligible is False
    assert decision.gate_reason == "recovery_not_enabled"
    assert decision.execution_mode is None


def test_recursive_hook_suppressed_when_recovery_active() -> None:
    """Recovery already in progress -> recursive_hook_suppressed."""
    resolved = _make_resolved_event()
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
    )
    decision = evaluate_recovery_gate(
        resolved,
        verif,
        enabled=True,
        attempts_used=0,
        recovery_in_progress=True,
    )
    assert decision.eligible is False
    assert decision.gate_reason == "recursive_hook_suppressed"
    assert decision.execution_mode is None


@pytest.mark.parametrize("attempts", [1, 2, 5, 10])
def test_retry_budget_exhausted(attempts: int) -> None:
    """attempts_used >= MAX_RECOVERY_ATTEMPTS (1) -> retry_budget_exhausted."""
    resolved = _make_resolved_event()
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
    )
    decision = evaluate_recovery_gate(
        resolved,
        verif,
        enabled=True,
        attempts_used=attempts,
        recovery_in_progress=False,
    )
    assert decision.eligible is False
    assert decision.gate_reason == "retry_budget_exhausted"
    assert decision.execution_mode is None


@pytest.mark.parametrize(
    ("bad_kwarg", "err_match"),
    [
        ({"enabled": 1}, "enabled must be a boolean"),
        ({"enabled": "true"}, "enabled must be a boolean"),
        ({"enabled": None}, "enabled must be a boolean"),
        ({"attempts_used": True}, "attempts_used must be an integer"),
        ({"attempts_used": -1}, "attempts_used must be non-negative"),
        ({"attempts_used": 1.0}, "attempts_used must be an integer"),
        ({"attempts_used": "0"}, "attempts_used must be an integer"),
        (
            {"recovery_in_progress": 0},
            "recovery_in_progress must be a boolean",
        ),
        (
            {"recovery_in_progress": "False"},
            "recovery_in_progress must be a boolean",
        ),
    ],
)
def test_strict_rejection_of_malformed_control_inputs(
    bad_kwarg: dict[str, Any], err_match: str
) -> None:
    """Strictly reject malformed control inputs without coercion."""
    resolved = _make_resolved_event()
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
    )
    kwargs: dict[str, Any] = {
        "enabled": True,
        "attempts_used": 0,
        "recovery_in_progress": False,
    }
    kwargs.update(bad_kwarg)

    with pytest.raises(ValueError, match=err_match):
        evaluate_recovery_gate(resolved, verif, **kwargs)


def test_invalid_resolved_event_or_verification_rejected() -> None:
    """Invalid event or verification summary types raise ValueError."""
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
    )
    with pytest.raises(
        ValueError, match="resolved_event must be a ResolvedHostHookEvent"
    ):
        evaluate_recovery_gate(
            "not_an_event",  # type: ignore[arg-type]
            verif,
        )

    resolved = _make_resolved_event()
    with pytest.raises(
        ValueError, match="verification must be a HookVerificationSummary"
    ):
        evaluate_recovery_gate(
            resolved,
            {"passed": False},  # type: ignore[arg-type]
        )


def test_gate_evaluation_is_pure_and_never_invokes_solver(
    tmp_path: Path,
) -> None:
    """Gate evaluation never calls solve, solve_swarm, agent, or mutates."""
    resolved = _make_resolved_event(workspace=str(tmp_path))
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
    )

    test_file = tmp_path / "sentinel.txt"
    test_file.write_text("untouched\n", encoding="utf-8")
    before_mtime = test_file.stat().st_mtime_ns

    with patch.object(
        HostAdapter, "solve", side_effect=AssertionError("solve called")
    ), patch.object(
        HostAdapter,
        "solve_swarm",
        side_effect=AssertionError("solve_swarm called"),
    ):
        dec = evaluate_recovery_gate(
            resolved,
            verif,
            enabled=True,
            attempts_used=0,
            recovery_in_progress=False,
        )
        assert dec.eligible is True
        assert dec.gate_reason == "eligible"

        # Check no workspace mutation occurred
        assert test_file.read_text(encoding="utf-8") == "untouched\n"
        assert test_file.stat().st_mtime_ns == before_mtime
        assert list(tmp_path.iterdir()) == [test_file]
