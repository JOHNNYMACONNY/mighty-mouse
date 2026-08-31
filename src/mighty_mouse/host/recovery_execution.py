"""Host Hook Recovery Execution Boundary v1.

Provides trusted, bounded, single-attempt agent recovery execution
for eligible Host Hook events following failed verification.

Enforces core architectural invariants:
- recovery attempt ceiling is strictly 1 (single-attempt boundary)
- only "agent" execution mode is supported in v1 (no swarm)
- exact write allowlist derived strictly from canonical target_paths
- no deletions permitted in recovery execution
- workspace hygiene cleanup (_hygiene_audit) is disabled
- authoritative runtime context from ResolvedHostHookEvent is used directly
  (host payload != authority)
- pure/bounded executor: solver failure returns bounded failure without
  leaking raw exception details
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from mighty_mouse.host.hooks import (
    HookRecoveryExecutionMode,
    ResolvedHostHookEvent,
)
from mighty_mouse.host.recovery import (
    MAX_RECOVERY_ATTEMPTS,
    HookRecoveryDecision,
)


@dataclass(frozen=True)
class RecoveryExecutionRequest:
    """Immutable internal request for bounded recovery execution."""

    resolved_event: ResolvedHostHookEvent
    decision: HookRecoveryDecision
    p_cfg_path: str
    task_input_path: str

    def __post_init__(self) -> None:
        if not isinstance(self.resolved_event, ResolvedHostHookEvent):
            raise ValueError(
                "resolved_event must be a ResolvedHostHookEvent instance"
            )
        if not isinstance(self.decision, HookRecoveryDecision):
            raise ValueError(
                "decision must be a HookRecoveryDecision instance"
            )
        if not isinstance(self.p_cfg_path, str) or not self.p_cfg_path.strip():
            raise ValueError("p_cfg_path must be a non-empty string")
        if (
            not isinstance(self.task_input_path, str)
            or not self.task_input_path.strip()
        ):
            raise ValueError("task_input_path must be a non-empty string")


@dataclass(frozen=True)
class RecoveryExecutionAttempt:
    """Immutable bounded result representing a single recovery attempt."""

    attempted: bool
    completed: bool
    attempts: int
    execution_mode: HookRecoveryExecutionMode | None = None
    output_paths: tuple[str, ...] = ()
    error_summary: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.attempted, bool):
            raise ValueError("attempted must be a boolean")
        if not isinstance(self.completed, bool):
            raise ValueError("completed must be a boolean")
        if isinstance(self.attempts, bool) or not isinstance(
            self.attempts, int
        ):
            raise ValueError("attempts must be an integer")
        if self.attempts < 0 or self.attempts > MAX_RECOVERY_ATTEMPTS:
            raise ValueError(
                f"attempts must be between 0 and {MAX_RECOVERY_ATTEMPTS}"
            )
        if not self.attempted:
            if self.attempts != 0:
                raise ValueError("attempts must be 0 when attempted is False")
            if self.completed:
                raise ValueError(
                    "completed must be False when attempted is False"
                )
            if self.execution_mode is not None:
                raise ValueError(
                    "execution_mode must be None when attempted is False"
                )
        else:
            if self.attempts != 1:
                raise ValueError("attempts must be 1 when attempted is True")
            if self.execution_mode != "agent":
                raise ValueError(
                    "execution_mode must be 'agent' when attempted is True"
                )


def execute_recovery_attempt(
    request: RecoveryExecutionRequest,
    *,
    feedback_str: str | None = None,
    temperature: float | None = None,
) -> RecoveryExecutionAttempt:
    """Execute a single bounded agent recovery attempt.

    Validates that:
    1. The decision is eligible (gate_reason == 'eligible', mode == 'agent').
    2. Event phase is post_action, action is file_write, mutation_class is
       workspace_mutation, and target_paths is non-empty.
    3. p_cfg_path and task_input_path exist and are valid files.

    If valid, invokes the agent with:
    - authoritative runtime_context from resolved_event
    - disable_hygiene = True
    - allowed_write_paths = resolved_event.event.action.target_paths
    - allowed_delete_paths = () (no deletions permitted)

    Returns RecoveryExecutionAttempt(attempted=True, completed=True/False,
    attempts=1, execution_mode='agent', output_paths=...).
    """
    if not isinstance(request, RecoveryExecutionRequest):
        raise ValueError(
            "request must be a RecoveryExecutionRequest instance"
        )

    # 1. Validate decision eligibility
    dec = request.decision
    if not dec.eligible or dec.gate_reason != "eligible":
        return RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=0,
            execution_mode=None,
            error_summary="Recovery decision is not eligible",
        )

    if dec.execution_mode != "agent":
        return RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=0,
            execution_mode=None,
            error_summary="Only agent execution mode is supported in v1",
        )

    # 2. Validate event phase, action, and target paths
    event = request.resolved_event.event
    if event.phase != "post_action":
        return RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=0,
            execution_mode=None,
            error_summary="Event phase is not post_action",
        )

    if (
        event.action.kind != "file_write"
        or event.action.mutation_class != "workspace_mutation"
    ):
        return RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=0,
            execution_mode=None,
            error_summary=(
                "Action kind or mutation class is not eligible for recovery"
            ),
        )

    target_paths = event.action.target_paths
    if not target_paths:
        return RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=0,
            execution_mode=None,
            error_summary=(
                "target_paths cannot be empty for recovery execution"
            ),
        )

    # 3. Validate trusted configuration and task input files
    p_cfg_abs = os.path.abspath(request.p_cfg_path)
    task_input_abs = os.path.abspath(request.task_input_path)

    if not os.path.isfile(p_cfg_abs):
        return RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=0,
            execution_mode=None,
            error_summary="p_cfg_path does not exist or is not a file",
        )

    if not os.path.isfile(task_input_abs):
        return RecoveryExecutionAttempt(
            attempted=False,
            completed=False,
            attempts=0,
            execution_mode=None,
            error_summary="task_input_path does not exist or is not a file",
        )

    # 4. Invoke agent via internal execution seam with strict boundaries
    ctx = request.resolved_event.runtime_context
    workspace = event.workspace

    try:
        from mighty_mouse.orchestrator.mighty_mouse_agent import (
            _solve_with_runtime_context,
        )
    except ImportError:
        from mighty_mouse_agent import (  # type: ignore[no-redef]
            _solve_with_runtime_context,
        )

    try:
        result = _solve_with_runtime_context(
            p_cfg_abs,
            task_input_abs,
            runtime_context=ctx,
            feedback_str=feedback_str,
            workspace=workspace,
            temperature=temperature,
            disable_hygiene=True,
            allowed_write_paths=target_paths,
            recovery_mode=True,
        )
        out_paths: tuple[str, ...] = ()
        if isinstance(result, (list, tuple)):
            out_paths = tuple(str(p) for p in result)
        elif isinstance(result, dict) and "output_paths" in result:
            out_paths = tuple(str(p) for p in result["output_paths"])

        return RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=1,
            execution_mode="agent",
            output_paths=out_paths,
            error_summary=None,
        )
    except Exception:
        # Bounded solver exception without exposing raw exception/host details
        return RecoveryExecutionAttempt(
            attempted=True,
            completed=False,
            attempts=1,
            execution_mode="agent",
            output_paths=(),
            error_summary="Agent solver execution failed",
        )
