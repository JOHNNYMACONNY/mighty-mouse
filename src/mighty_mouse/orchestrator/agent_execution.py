"""Private Agent Execution coordinator.

This module owns bounded execution and output-coverage recovery while the
composition root prepares prompts, clients, and opaque response adapters.
"""

from __future__ import annotations

import difflib
import sys
from dataclasses import dataclass, replace
from typing import Any, Callable, Sequence

try:
    from mighty_mouse.orchestrator.response_attempt import (
        ParserAdapter,
        ResponseAttemptContext,
        ResponseAttemptResult,
    )
except ImportError:
    from response_attempt import (  # type: ignore[no-redef]
        ParserAdapter,
        ResponseAttemptContext,
        ResponseAttemptResult,
    )

try:
    from mighty_mouse.v2.records import ComputeScalingPolicy
except ImportError:
    try:
        from v2.records import ComputeScalingPolicy  # type: ignore[no-redef]
    except ImportError:
        ComputeScalingPolicy = Any  # type: ignore[misc,assignment]


@dataclass(frozen=True)
class _AgentExecutionRequest:
    """Prepared inputs crossing the private Agent Execution seam."""

    response_attempt_context: ResponseAttemptContext
    expected_files: tuple[str, ...]
    conflict_detected: bool
    injection_reason: str | None
    is_conflict_routing_validation: bool
    deletable_expected_files: tuple[str, ...]
    scaling_policy: Any | None = None


@dataclass(frozen=True)
class _AgentExecutionOutcome:
    """Execution-derived values returned to the composition root."""

    response: str | None
    output_paths: tuple[str, ...]
    usage_history: tuple[dict[str, Any], ...]
    schema_error: bool
    coverage_recovery_attempts: int
    coverage_recovery_triggered: bool
    coverage_missing_files: tuple[str, ...]
    coverage_recovery_success: bool
    coverage_recovery_disallowed_reason: str | None
    pass_type: str


ResponseAttemptRunner = Callable[
    [ResponseAttemptContext, ParserAdapter | None], ResponseAttemptResult
]
ResponseApplicationAdapter = Callable[
    [str, ResponseAttemptContext], Sequence[str]
]
ResponsePlanningAdapter = Callable[
    [str, ResponseAttemptContext], Any
]


def _evaluate_output_coverage_policy(
    expected_files: Sequence[str],
    cumulative_output_paths: Sequence[str],
    *,
    conflict_detected: bool,
    injection_reason: str | None,
    is_conflict_routing_validation: bool,
    deletable_expected_files: Sequence[str],
    coverage_recovery_attempts: int,
) -> tuple[list[str], str | None]:
    missing_files = [
        path for path in expected_files if path not in cumulative_output_paths
    ]
    if not missing_files:
        return [], None

    if conflict_detected:
        disallowed_reason = "CONFLICT_DETECTED"
    elif injection_reason == "CONFLICT_REJECTED":
        disallowed_reason = "CONFLICT_REJECTED"
    elif is_conflict_routing_validation:
        disallowed_reason = "CONFLICT_ROUTING_VALIDATION_TASK"
    elif any(path in deletable_expected_files for path in missing_files):
        disallowed_reason = "DELETABLE_FILE_EXCLUSION"
    elif coverage_recovery_attempts >= 1:
        disallowed_reason = "MAX_ATTEMPTS_REACHED"
    else:
        disallowed_reason = None

    return missing_files, disallowed_reason


def _compute_plan_distance(canon_a: str, canon_b: str) -> int:
    """Compute pairwise line-edit distance between two canonical plans."""
    if canon_a == canon_b:
        return 0
    lines_a = canon_a.splitlines()
    lines_b = canon_b.splitlines()
    matcher = difflib.SequenceMatcher(None, lines_a, lines_b, autojunk=False)
    distance = 0
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag != "equal":
            distance += max(i2 - i1, j2 - j1)
    return distance


def _select_consensus_winner(
    valid_candidates: list[tuple[int, str, Any, str]],
    consensus_strategy: str,
    total_variations: int,
) -> tuple[str, Any] | None:
    """Select single winning candidate via deterministic consensus strategy.

    Each item in valid_candidates is:
    (cand_idx, response_text, plan_or_paths, canonical_rep).
    """
    if not valid_candidates:
        return None

    if consensus_strategy == "unanimous":
        if len(valid_candidates) != total_variations:
            return None
        first_rep = valid_candidates[0][3]
        if all(cand[3] == first_rep for cand in valid_candidates):
            return valid_candidates[0][1], valid_candidates[0][2]
        return None

    # min_diff strategy (default)
    if len(valid_candidates) == 1:
        return valid_candidates[0][1], valid_candidates[0][2]

    best_cand = None
    best_dist = float("inf")
    best_idx = float("inf")

    for i, (idx_i, resp_i, plan_i, canon_i) in enumerate(valid_candidates):
        total_dist = 0
        for j, (_, _, _, canon_j) in enumerate(valid_candidates):
            if i != j:
                total_dist += _compute_plan_distance(canon_i, canon_j)
        if (
            total_dist < best_dist
            or (total_dist == best_dist and idx_i < best_idx)
        ):
            best_dist = total_dist
            best_idx = idx_i
            best_cand = (resp_i, plan_i)

    return best_cand


def _execute_agent_execution(
    request: _AgentExecutionRequest,
    *,
    response_attempt_runner: ResponseAttemptRunner,
    response_application_adapter: ResponseApplicationAdapter | None,
    response_planning_adapter: ResponsePlanningAdapter | None = None,
) -> _AgentExecutionOutcome:
    """Execute prepared inputs through one bounded Agent Execution seam."""

    base_max_attempts = request.response_attempt_context.max_attempts
    effective_max_attempts = base_max_attempts
    attempt = request.response_attempt_context.attempt
    current_user_prompt = request.response_attempt_context.user_prompt
    usage_history: list[dict[str, Any]] = []
    cumulative_output_paths: list[str] = []
    coverage_recovery_attempts = 0
    coverage_recovery_triggered = False
    coverage_missing_files: list[str] = []
    coverage_recovery_success = False
    coverage_recovery_disallowed_reason = None
    response: str | None = None
    schema_error = False
    pass_type = "clean"
    scaling_policy = request.scaling_policy

    while attempt <= effective_max_attempts:
        print(
            f"[agent] Attempt {attempt}/{effective_max_attempts} starting...",
            file=sys.stderr,
        )
        sys.stdout.flush()

        if (
            scaling_policy is not None
            and response_application_adapter is not None
        ):
            # Scaled candidate execution
            variations = getattr(scaling_policy, "variations", 1)
            temp_schedule = getattr(
                scaling_policy,
                "effective_temperature_schedule",
                lambda: (0.0,),
            )()
            consensus_strategy = getattr(
                scaling_policy,
                "consensus_strategy",
                "min_diff",
            )

            # Store plan objects or output paths during planning
            valid_candidates: list[tuple[int, str, Any, str]] = []

            for cand_idx in range(variations):
                if cand_idx < len(temp_schedule):
                    cand_temp = temp_schedule[cand_idx]
                else:
                    cand_temp = temp_schedule[-1]
                cand_context = replace(
                    request.response_attempt_context,
                    user_prompt=current_user_prompt,
                    attempt=attempt,
                    max_attempts=effective_max_attempts,
                )
                object.__setattr__(
                    cand_context,
                    "_sampling_temperature",
                    cand_temp,
                )
                object.__setattr__(
                    cand_context,
                    "_candidate_index",
                    cand_idx,
                )

                cand_collected_plans: list[Any] = []

                def cand_parser(
                    resp_text: str,
                    ctx: ResponseAttemptContext,
                ) -> Sequence[str]:
                    if response_planning_adapter is not None:
                        plan = response_planning_adapter(resp_text, ctx)
                        cand_collected_plans.append(plan)
                        if hasattr(plan, "output_paths"):
                            return plan.output_paths
                        return plan
                    return [resp_text]

                cand_result = response_attempt_runner(
                    cand_context,
                    cand_parser,
                )
                usage_history.extend(cand_result.usage_history)

                if (
                    not cand_result.failed
                    and cand_result.response is not None
                    and cand_result.output_paths
                ):
                    resp_str = cand_result.response
                    if cand_collected_plans:
                        plan_obj = cand_collected_plans[0]
                    else:
                        plan_obj = cand_result.output_paths
                    if hasattr(plan_obj, "canonical_representation"):
                        canon_rep = plan_obj.canonical_representation()
                    else:
                        canon_rep = resp_str
                    valid_candidates.append(
                        (cand_idx, resp_str, plan_obj, canon_rep)
                    )

            attempt += 1

            winner = _select_consensus_winner(
                valid_candidates,
                consensus_strategy,
                variations,
            )

            if winner is None:
                schema_error = len(valid_candidates) == 0
                pass_type = "failed"
                break

            winning_response, _ = winner
            response = winning_response

            applied_paths = response_application_adapter(
                winning_response,
                replace(
                    request.response_attempt_context,
                    attempt=attempt - 1,
                ),
            )
            cumulative_output_paths.extend(applied_paths)

        else:
            # Unscaled single execution path (legacy)
            attempt_context = replace(
                request.response_attempt_context,
                user_prompt=current_user_prompt,
                attempt=attempt,
                max_attempts=effective_max_attempts,
            )
            attempt_result = response_attempt_runner(
                attempt_context,
                response_application_adapter,
            )
            usage_history.extend(attempt_result.usage_history)
            current_user_prompt = attempt_result.next_user_prompt
            attempt = attempt_result.next_attempt
            schema_error = attempt_result.schema_error

            if attempt_result.failed:
                pass_type = "failed"
                break

            response = attempt_result.response

            if response_application_adapter is None:
                pass_type = "clean"
                break

            cumulative_output_paths.extend(attempt_result.output_paths)

        missing_files, disallowed_reason = _evaluate_output_coverage_policy(
            request.expected_files,
            cumulative_output_paths,
            conflict_detected=request.conflict_detected,
            injection_reason=request.injection_reason,
            is_conflict_routing_validation=(
                request.is_conflict_routing_validation
            ),
            deletable_expected_files=request.deletable_expected_files,
            coverage_recovery_attempts=coverage_recovery_attempts,
        )
        if missing_files:
            coverage_missing_files = missing_files

            if disallowed_reason:
                coverage_recovery_disallowed_reason = disallowed_reason
                print(
                    "[agent] Missing expected files "
                    f"{missing_files} detected but recovery is forbidden: "
                    f"{disallowed_reason}",
                    file=sys.stderr,
                )
                pass_type = "failed"
                break

            coverage_recovery_attempts += 1
            coverage_recovery_triggered = True
            print(
                "[agent] Missing expected files detected: "
                f"{missing_files}. Issuing targeted recovery reprompt...",
                file=sys.stderr,
            )
            missing_list_str = "\n".join(
                f"- {path}" for path in missing_files
            )
            current_user_prompt += (
                "\n\nCRITICAL OMISSION DETECTED:\n"
                "Your previous response failed to provide the implementation "
                "for the following required files:\n"
                f"{missing_list_str}\n\n"
                "You MUST provide the complete implementation for these files "
                "now using the correct format (```python:path/to/file.py).\n"
                "Do NOT rewrite files you have already provided. Only provide "
                "the missing file blocks."
            )
            effective_max_attempts = base_max_attempts + 1
            continue

        if coverage_recovery_triggered:
            coverage_recovery_success = True
            pass_type = "recovered"
            print(
                "[agent] Coverage recovery successfully recovered missing "
                "expected files.",
                file=sys.stderr,
            )
        else:
            pass_type = "clean"
        break

    return _AgentExecutionOutcome(
        response=response,
        output_paths=tuple(cumulative_output_paths),
        usage_history=tuple(usage_history),
        schema_error=schema_error,
        coverage_recovery_attempts=coverage_recovery_attempts,
        coverage_recovery_triggered=coverage_recovery_triggered,
        coverage_missing_files=tuple(coverage_missing_files),
        coverage_recovery_success=coverage_recovery_success,
        coverage_recovery_disallowed_reason=(
            coverage_recovery_disallowed_reason
        ),
        pass_type=pass_type,
    )
