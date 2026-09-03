"""Tests for Host Hook Recovery Execution Boundary v1."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
import json
from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
import yaml

from mighty_mouse.host.adapter import (
    AdapterRuntimeContext,
    ExecutionProfile,
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
from mighty_mouse.host.recovery_execution import (
    RecoveryExecutionAttempt,
    RecoveryExecutionRequest,
    execute_recovery_attempt,
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
    target_paths: tuple[str, ...] = ("src/main.py",),
) -> ResolvedHostHookEvent:
    action = HostHookAction(
        kind=kind,  # type: ignore[arg-type]
        mutation_class=mutation_class,  # type: ignore[arg-type]
        target_paths=target_paths,
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


def _setup_test_files(tmp_path: Path) -> tuple[str, str]:
    """Create minimal valid p_cfg and task_input files."""
    cfg_file = tmp_path / "model_config.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "model": "test-model",
                "temperature": 0.0,
                "provider": "sim",
                "allow_simulation": True,
            }
        ),
        encoding="utf-8",
    )
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps({"id": "task-1", "instruction": "fix bug"}),
        encoding="utf-8",
    )
    return str(cfg_file), str(task_file)


def test_recovery_execution_request_and_attempt_frozen() -> None:
    """Request and Attempt objects must be immutable frozen dataclasses."""
    resolved = _make_resolved_event()
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )
    req = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path="cfg.yaml",
        task_input_path="task.json",
    )
    with pytest.raises(FrozenInstanceError):
        req.p_cfg_path = "other.yaml"  # type: ignore[misc]

    att = RecoveryExecutionAttempt(
        attempted=True,
        completed=True,
        attempts=1,
        execution_mode="agent",
        output_paths=("src/main.py",),
    )
    with pytest.raises(FrozenInstanceError):
        att.completed = False  # type: ignore[misc]


def test_recovery_execution_attempt_invariants() -> None:
    """RecoveryExecutionAttempt strictly enforces internal invariants."""
    with pytest.raises(ValueError, match="attempts must be an integer"):
        RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=True,  # type: ignore[arg-type]
            execution_mode="agent",
        )

    with pytest.raises(ValueError, match="attempts must be between 0 and 1"):
        RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=2,
            execution_mode="agent",
        )

    with pytest.raises(ValueError, match="execution_mode must be 'agent'"):
        RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=1,
            execution_mode="swarm",
        )

    with pytest.raises(ValueError, match="execution_mode must be None"):
        RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=0,
            execution_mode="agent",
        )

    # Contradictory states:
    with pytest.raises(
        ValueError, match="attempts must be 0 when attempted is False"
    ):
        RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=1,
        )

    with pytest.raises(
        ValueError, match="completed must be False when attempted is False"
    ):
        RecoveryExecutionAttempt(
            attempted=False,
            completed=True,
            attempts=0,
        )

    with pytest.raises(
        ValueError, match="attempts must be 1 when attempted is True"
    ):
        RecoveryExecutionAttempt(
            attempted=True,
            completed=False,
            attempts=0,
            execution_mode="agent",
        )


def test_execute_recovery_attempt_successful_invocation(
    tmp_path: Path,
) -> None:
    """Eligible request invokes agent once with target_paths allowlist."""
    cfg_path, task_path = _setup_test_files(tmp_path)
    resolved = _make_resolved_event(
        workspace=str(tmp_path), target_paths=("src/main.py",)
    )
    verif = HookVerificationSummary(
        occurred=True, passed=False, summary="Verification failed"
    )
    decision = evaluate_recovery_gate(resolved, verif, enabled=True)

    request = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=cfg_path,
        task_input_path=task_path,
    )

    with patch(
        "mighty_mouse.orchestrator.mighty_mouse_agent."
        "_solve_with_runtime_context",
        return_value=["src/main.py"],
    ) as mock_solve:
        attempt = execute_recovery_attempt(request)

        assert mock_solve.call_count == 1
        _, kwargs = mock_solve.call_args
        assert kwargs["runtime_context"] == resolved.runtime_context
        assert kwargs["disable_hygiene"] is True
        assert kwargs["allowed_write_paths"] == ("src/main.py",)
        assert kwargs["workspace"] == str(tmp_path)

        assert attempt.attempted is True
        assert attempt.completed is True
        assert attempt.attempts == 1
        assert attempt.execution_mode == "agent"
        assert attempt.output_paths == ("src/main.py",)
        assert attempt.error_summary is None


def test_execute_recovery_attempt_ineligible_decision_invokes_nothing(
    tmp_path: Path,
) -> None:
    """Ineligible recovery decision returns attempted=False."""
    cfg_path, task_path = _setup_test_files(tmp_path)
    resolved = _make_resolved_event(workspace=str(tmp_path))
    verif = HookVerificationSummary(
        occurred=True, passed=True, summary="Passed"
    )
    decision = evaluate_recovery_gate(resolved, verif, enabled=True)
    assert decision.eligible is False

    request = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=cfg_path,
        task_input_path=task_path,
    )

    with patch(
        "mighty_mouse.orchestrator.mighty_mouse_agent."
        "_solve_with_runtime_context"
    ) as mock_solve:
        attempt = execute_recovery_attempt(request)
        assert mock_solve.call_count == 0
        assert attempt.attempted is False
        assert attempt.completed is False
        assert attempt.attempts == 0
        assert attempt.execution_mode is None
        assert attempt.error_summary == "Recovery decision is not eligible"


def test_execute_recovery_attempt_missing_config_or_task_file(
    tmp_path: Path,
) -> None:
    """Non-existent config or task input file returns attempted=False."""
    resolved = _make_resolved_event(workspace=str(tmp_path))
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )

    # Missing config
    req_bad_cfg = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=str(tmp_path / "nonexistent.yaml"),
        task_input_path=str(tmp_path / "task.json"),
    )
    attempt = execute_recovery_attempt(req_bad_cfg)
    assert attempt.attempted is False
    assert attempt.attempts == 0
    assert "p_cfg_path does not exist" in str(attempt.error_summary)

    # Missing task
    cfg_path, _ = _setup_test_files(tmp_path)
    req_bad_task = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=cfg_path,
        task_input_path=str(tmp_path / "nonexistent_task.json"),
    )
    attempt = execute_recovery_attempt(req_bad_task)
    assert attempt.attempted is False
    assert attempt.attempts == 0
    assert "task_input_path does not exist" in str(attempt.error_summary)


def test_execute_recovery_attempt_empty_target_paths_rejected(
    tmp_path: Path,
) -> None:
    """Request with empty target_paths fails closed before invoking solver."""
    cfg_path, task_path = _setup_test_files(tmp_path)
    resolved = _make_resolved_event(
        workspace=str(tmp_path), target_paths=()
    )
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )
    req = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=cfg_path,
        task_input_path=task_path,
    )
    with patch(
        "mighty_mouse.orchestrator.mighty_mouse_agent."
        "_solve_with_runtime_context"
    ) as mock_solve:
        attempt = execute_recovery_attempt(req)
        assert mock_solve.call_count == 0
        assert attempt.attempted is False
        assert "target_paths cannot be empty" in str(attempt.error_summary)


def test_execute_recovery_attempt_solver_exception_returns_bounded_failure(
    tmp_path: Path,
) -> None:
    """Solver exception yields attempted=True, completed=False bounded."""
    cfg_path, task_path = _setup_test_files(tmp_path)
    resolved = _make_resolved_event(
        workspace=str(tmp_path), target_paths=("src/main.py",)
    )
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )
    request = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=cfg_path,
        task_input_path=task_path,
    )

    with patch(
        "mighty_mouse.orchestrator.mighty_mouse_agent."
        "_solve_with_runtime_context",
        side_effect=RuntimeError("sensitive secret in traceback"),
    ):
        attempt = execute_recovery_attempt(request)

        assert attempt.attempted is True
        assert attempt.completed is False
        assert attempt.attempts == 1
        assert attempt.execution_mode == "agent"
        assert attempt.output_paths == ()
        assert attempt.error_summary == "Agent solver execution failed"
        assert "sensitive" not in str(attempt.error_summary)


def test_recovery_execution_does_not_purge_unrelated_python_files(
    tmp_path: Path,
) -> None:
    """Recovery execution (disable_hygiene=True) preserves root .py files."""
    cfg_path, task_path = _setup_test_files(tmp_path)

    # Create unrelated sentinel .py files in workspace root
    sentinel1 = tmp_path / "sentinel_custom.py"
    sentinel1.write_text("# important custom script\n", encoding="utf-8")
    sentinel2 = tmp_path / "scratch_work.py"
    sentinel2.write_text("# scratch\n", encoding="utf-8")

    resolved = _make_resolved_event(
        workspace=str(tmp_path), target_paths=("src/main.py",)
    )
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )
    request = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=cfg_path,
        task_input_path=task_path,
    )

    with patch(
        "mighty_mouse.orchestrator.mighty_mouse_agent."
        "_execute_agent_execution"
    ) as mock_exec, patch(
        "mighty_mouse.orchestrator.mighty_mouse_agent._write_run_metadata"
    ):
        mock_outcome = MagicMock()
        mock_outcome.usage_history = []
        mock_outcome.output_paths = ["src/main.py"]
        mock_outcome.schema_error = None
        mock_outcome.coverage_recovery_attempts = 0
        mock_outcome.coverage_recovery_triggered = False
        mock_outcome.coverage_missing_files = []
        mock_outcome.coverage_recovery_success = False
        mock_outcome.coverage_recovery_disallowed_reason = None
        mock_outcome.pass_type = "single_pass"
        mock_outcome.response = None
        mock_exec.return_value = mock_outcome

        attempt = execute_recovery_attempt(request)
        assert attempt.attempted is True
        assert attempt.completed is True

        # Assert sentinels were not deleted by _hygiene_audit
        assert sentinel1.exists()
        assert sentinel2.exists()
        assert sentinel1.read_text(encoding="utf-8") == (
            "# important custom script\n"
        )


@pytest.mark.parametrize(
    ("phase", "kind", "mutation_class", "err_substring"),
    [
        (
            "pre_action",
            "file_write",
            "workspace_mutation",
            "phase is not post_action",
        ),
        (
            "post_action",
            "shell_command",
            "workspace_mutation",
            "Action kind or mutation class is not eligible",
        ),
        (
            "post_action",
            "file_write",
            "read_only",
            "Action kind or mutation class is not eligible",
        ),
    ],
)
def test_execute_recovery_attempt_invalid_phase_or_action(
    tmp_path: Path,
    phase: str,
    kind: str,
    mutation_class: str,
    err_substring: str,
) -> None:
    """Non-post_action / non-file_write / non-workspace fail closed."""
    cfg_path, task_path = _setup_test_files(tmp_path)
    resolved = _make_resolved_event(
        workspace=str(tmp_path),
        phase=phase,
        kind=kind,
        mutation_class=mutation_class,
        target_paths=("src/main.py",),
    )
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )
    request = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=cfg_path,
        task_input_path=task_path,
    )
    attempt = execute_recovery_attempt(request)
    assert attempt.attempted is False
    assert attempt.attempts == 0
    assert err_substring in str(attempt.error_summary)


def test_recovery_execution_enforces_zero_deletions_even_with_task_deletables(
    tmp_path: Path,
) -> None:
    """Recovery execution refuses deletions even with deletable_files."""
    cfg_file = tmp_path / "model_config.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "model": "test-model",
                "temperature": 0.0,
                "provider": "sim",
                "allow_simulation": True,
            }
        ),
        encoding="utf-8",
    )
    # Task explicitly authorizes deletion of victim.py
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps(
            {
                "id": "task-1",
                "deletable_files": ["victim.py"],
                "expected_files": ["src/main.py"],
            }
        ),
        encoding="utf-8",
    )

    victim = tmp_path / "victim.py"
    victim.write_text("precious code\n", encoding="utf-8")

    resolved = _make_resolved_event(
        workspace=str(tmp_path), target_paths=("src/main.py",)
    )
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )
    request = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=str(cfg_file),
        task_input_path=str(task_file),
    )

    # Model emits a delete block for victim.py
    delete_response = """```delete:victim.py
```"""

    with patch(
        "mighty_mouse.orchestrator.gemini_client."
        "GeminiClient.generate_content",
        return_value=delete_response,
    ):
        attempt = execute_recovery_attempt(request)
        # Deletion not permitted -> response application raises ValueError,
        # leading to completed=False without deleting victim.py
        assert attempt.attempted is True
        assert attempt.completed is False
        assert victim.exists()
        assert victim.read_text(encoding="utf-8") == "precious code\n"


def test_recovery_execution_performs_strictly_one_provider_generation(
    tmp_path: Path,
) -> None:
    """Recovery execution makes 1 provider call, never retrying on error."""
    cfg_file = tmp_path / "model_config.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "model": "test-model",
                "temperature": 0.0,
                "provider": "sim",
                "allow_simulation": True,
            }
        ),
        encoding="utf-8",
    )
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps({"id": "task-1", "expected_files": ["src/main.py"]}),
        encoding="utf-8",
    )

    resolved = _make_resolved_event(
        workspace=str(tmp_path), target_paths=("src/main.py",)
    )
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )
    request = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=str(cfg_file),
        task_input_path=str(task_file),
    )

    # Malformed output that produces schema error
    bad_response = "I am not returning valid fenced code blocks."

    with patch(
        "mighty_mouse.orchestrator.gemini_client."
        "GeminiClient.generate_content",
        return_value=bad_response,
    ) as mock_gen:
        attempt = execute_recovery_attempt(request)

        # Must have called provider exactly ONCE
        assert mock_gen.call_count == 1
        assert attempt.attempted is True
        assert attempt.completed is True
        assert attempt.attempts == 1
        assert attempt.output_paths == ()


def test_recovery_execution_succeeds_with_incidental_checklist_sidecar(
    tmp_path: Path,
) -> None:
    """Ticket 09: Recovery applies target even if model outputs checklist."""
    cfg_file = tmp_path / "model_config.yaml"
    cfg_file.write_text(
        yaml.safe_dump(
            {
                "model": "test-model",
                "temperature": 0.0,
                "provider": "sim",
                "allow_simulation": True,
            }
        ),
        encoding="utf-8",
    )
    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps({"id": "task-1", "expected_files": ["src/main.py"]}),
        encoding="utf-8",
    )

    resolved = _make_resolved_event(
        workspace=str(tmp_path), target_paths=("src/main.py",)
    )
    decision = HookRecoveryDecision(
        eligible=True,
        gate_reason="eligible",
        summary="eligible",
        execution_mode="agent",
    )
    request = RecoveryExecutionRequest(
        resolved_event=resolved,
        decision=decision,
        p_cfg_path=str(cfg_file),
        task_input_path=str(task_file),
    )

    recovery_response = """# Mighty Mouse Checklist
- [ ] Investigate failure
- [ ] Apply fix to main.py

```python:src/main.py
def fixed():
    return True
```"""

    with patch(
        "mighty_mouse.orchestrator.gemini_client."
        "GeminiClient.generate_content",
        return_value=recovery_response,
    ):
        attempt = execute_recovery_attempt(request)
        assert attempt.attempted is True
        assert attempt.completed is True
        assert attempt.output_paths == ("src/main.py",)
        assert (tmp_path / "src" / "main.py").exists()
        assert not (tmp_path / "CHECKLIST.md").exists()
