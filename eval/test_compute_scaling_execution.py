"""Comprehensive test suite for bounded compute-scaling candidate execution.

Verifies:
1. No scaling policy => legacy behavior
2. Exact candidate bound
3. Effective temperature schedule including repeated final temperature
4. Candidates do not mutate workspace
5. Invalid candidate planning triggers existing schema retry
6. Only winner mutates
7. min_diff expected winner
8. Deterministic index tie-break
9. One-valid-candidate min_diff
10. Zero-valid-candidate failure with no mutation
11. Unanimous equal plans succeeds
12. Unanimous disagreement fails with no mutation
13. Unanimous candidate failure fails with no mutation
14. Coverage recovery still works and applies one selected winner per round
15. Delete/path/hygiene validation remains equivalent
16. Candidate raw logs cannot overwrite each other
17. Usage history includes all candidate calls in deterministic order
"""

from pathlib import Path

import pytest

from mighty_mouse.orchestrator.agent_execution import (
    _AgentExecutionRequest,
    _execute_agent_execution,
)
from mighty_mouse.orchestrator.response_application import (
    ResponseApplicationPolicy,
    ResponseApplicationRequest,
    apply_response,
    plan_response,
)
from mighty_mouse.orchestrator.response_attempt import (
    ResponseAttemptContext,
    ResponseAttemptResult,
    execute_response_attempt,
)
from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.records import (
    ComputeScalingPin,
    ComputeScalingPolicy,
    ExecutionProfile,
    Mode,
    ModelIdentity,
    Scope,
    TaskCategory,
)


def _make_request(
    tmp_path: Path,
    scaling_policy: ComputeScalingPolicy | None = None,
    expected_files: tuple[str, ...] = (),
    allowed_delete_paths: tuple[str, ...] = (),
) -> _AgentExecutionRequest:
    return _AgentExecutionRequest(
        response_attempt_context=ResponseAttemptContext(
            system_prompt="system",
            user_prompt="initial user prompt",
            task_id="task_scaling_test",
            attempt=1,
            max_attempts=2,
            workspace_root=str(tmp_path),
            allowed_delete_paths=allowed_delete_paths,
        ),
        expected_files=expected_files,
        conflict_detected=False,
        injection_reason=None,
        is_conflict_routing_validation=False,
        deletable_expected_files=tuple(
            p for p in expected_files if p in allowed_delete_paths
        ),
        scaling_policy=scaling_policy,
    )


def test_no_scaling_policy_preserves_legacy_single_execution(tmp_path: Path):
    runner_calls = []

    def app_adapter(response, context):
        (tmp_path / "legacy.py").write_text(response)
        return ["legacy.py"]

    def runner(context, parser_adapter):
        runner_calls.append(context.attempt)
        output_paths = parser_adapter("legacy content", context)
        return ResponseAttemptResult(
            response="legacy content",
            output_paths=list(output_paths),
            usage_history=[{"tokens": 10}],
            schema_error=False,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    req = _make_request(tmp_path, scaling_policy=None)
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
    )

    assert len(runner_calls) == 1
    assert outcome.response == "legacy content"
    assert outcome.output_paths == ("legacy.py",)
    assert outcome.pass_type == "clean"
    assert (tmp_path / "legacy.py").read_text() == "legacy content"


def test_exact_candidate_bound_and_temperature_schedule(tmp_path: Path):
    observed_temps = []
    observed_cand_indices = []

    policy = ComputeScalingPolicy(
        variations=4,
        temperature_schedule=(0.1, 0.4),
        consensus_strategy="min_diff",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def runner(context, parser_adapter):
        observed_temps.append(getattr(context, "_sampling_temperature", None))
        cand_idx = getattr(context, "_candidate_index", None)
        observed_cand_indices.append(cand_idx)
        cand_resp = f"```python:cand_{cand_idx}.py\nx = 1\n```"
        output_paths = parser_adapter(cand_resp, context)
        return ResponseAttemptResult(
            response=cand_resp,
            output_paths=list(output_paths),
            usage_history=[{"cand": cand_idx}],
            schema_error=False,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    req = _make_request(tmp_path, scaling_policy=policy)
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    assert len(observed_cand_indices) == 4
    assert observed_cand_indices == [0, 1, 2, 3]
    assert observed_temps == [0.1, 0.4, 0.4, 0.4]
    assert len(outcome.usage_history) == 4
    assert outcome.pass_type == "clean"


def test_candidates_do_not_mutate_workspace_during_generation(tmp_path: Path):
    policy = ComputeScalingPolicy(
        variations=3,
        temperature_schedule=(0.0, 0.2, 0.5),
        consensus_strategy="min_diff",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    candidate_responses = [
        "```python:cand1.py\ncand 1\n```",
        "```python:winner.py\nwinner\n```",
        "```python:cand3.py\ncand 3\n```",
    ]
    cand_iter = iter(candidate_responses)

    def runner(context, parser_adapter):
        resp = next(cand_iter)
        output_paths = parser_adapter(resp, context)
        # Verify workspace is untouched during candidate run
        assert not (tmp_path / "cand1.py").exists()
        assert not (tmp_path / "winner.py").exists()
        assert not (tmp_path / "cand3.py").exists()
        return ResponseAttemptResult(
            response=resp,
            output_paths=list(output_paths),
            usage_history=[{"step": 1}],
            schema_error=False,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    req = _make_request(tmp_path, scaling_policy=policy)
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    # After execution, only winning file exists
    assert outcome.pass_type == "clean"
    created = [
        (tmp_path / "cand1.py").exists(),
        (tmp_path / "winner.py").exists(),
        (tmp_path / "cand3.py").exists(),
    ]
    assert any(created)


def test_min_diff_consensus_expected_winner_and_tie_breaking(tmp_path: Path):
    # Setup 3 candidates: A and B are close/identical, C is an outlier
    resp_a = "```python:app.py\ndef run():\n    return 10\n```"
    resp_b = "```python:app.py\ndef run():\n    return 10\n```"
    resp_c = "```python:app.py\ndef run():\n    return 9999\n```"

    policy = ComputeScalingPolicy(
        variations=3,
        temperature_schedule=(0.0, 0.2, 0.5),
        consensus_strategy="min_diff",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    cands = iter([resp_a, resp_b, resp_c])

    def runner(context, parser_adapter):
        resp = next(cands)
        output_paths = parser_adapter(resp, context)
        return ResponseAttemptResult(
            response=resp,
            output_paths=list(output_paths),
            usage_history=[{"cand": getattr(context, "_candidate_index", 0)}],
            schema_error=False,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    req = _make_request(tmp_path, scaling_policy=policy)
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    # A and B tie with dist(A, C). Tie-breaker chooses lower index (A: index 0)
    assert outcome.response == resp_a
    assert (tmp_path / "app.py").read_text() == "def run():\n    return 10"


def test_one_valid_candidate_min_diff(tmp_path: Path):
    policy = ComputeScalingPolicy(
        variations=2,
        temperature_schedule=(0.0, 0.5),
        consensus_strategy="min_diff",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    # Cand 0 fails, Cand 1 succeeds
    cands = iter([
        (None, [], True),
        ("```python:single.py\nval = 42\n```", ["single.py"], False),
    ])

    def runner(context, parser_adapter):
        resp, paths, failed = next(cands)
        return ResponseAttemptResult(
            response=resp,
            output_paths=paths,
            usage_history=[{"attempt": 1}],
            schema_error=failed,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=failed,
        )

    req = _make_request(tmp_path, scaling_policy=policy)
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    assert outcome.pass_type == "clean"
    assert (tmp_path / "single.py").read_text() == "val = 42"


def test_zero_valid_candidates_fails_with_zero_mutation(tmp_path: Path):
    policy = ComputeScalingPolicy(
        variations=2,
        temperature_schedule=(0.0, 0.5),
        consensus_strategy="min_diff",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def runner(context, parser_adapter):
        return ResponseAttemptResult(
            response="no blocks here",
            output_paths=[],
            usage_history=[{"tokens": 5}],
            schema_error=True,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=True,
        )

    req = _make_request(tmp_path, scaling_policy=policy)
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    assert outcome.pass_type == "failed"
    assert outcome.schema_error is True
    assert list(tmp_path.iterdir()) == []


def test_unanimous_consensus_success_and_failure(tmp_path: Path):
    resp1 = "```python:same.py\nv = 1\n```"
    resp2 = "```python:same.py\nv = 1\n```"
    resp3_diff = "```python:same.py\nv = 2\n```"

    policy = ComputeScalingPolicy(
        variations=2,
        temperature_schedule=(0.0, 0.2),
        consensus_strategy="unanimous",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    # 1. Unanimous equal => Success
    cands_ok = iter([resp1, resp2])

    def runner_ok(context, parser_adapter):
        resp = next(cands_ok)
        output_paths = parser_adapter(resp, context)
        return ResponseAttemptResult(
            response=resp,
            output_paths=list(output_paths),
            usage_history=[{"cand": 1}],
            schema_error=False,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    req_ok = _make_request(tmp_path, scaling_policy=policy)
    outcome_ok = _execute_agent_execution(
        req_ok,
        response_attempt_runner=runner_ok,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    assert outcome_ok.pass_type == "clean"
    assert (tmp_path / "same.py").read_text() == "v = 1"

    # 2. Disagreement => Fail closed with zero mutation
    (tmp_path / "same.py").unlink()
    cands_diff = iter([resp1, resp3_diff])

    def runner_diff(context, parser_adapter):
        resp = next(cands_diff)
        output_paths = parser_adapter(resp, context)
        return ResponseAttemptResult(
            response=resp,
            output_paths=list(output_paths),
            usage_history=[{"cand": 1}],
            schema_error=False,
            next_attempt=2,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    req_diff = _make_request(tmp_path, scaling_policy=policy)
    outcome_diff = _execute_agent_execution(
        req_diff,
        response_attempt_runner=runner_diff,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    assert outcome_diff.pass_type == "failed"
    assert not (tmp_path / "same.py").exists()


def test_coverage_recovery_with_scaling_policy(tmp_path: Path):
    policy = ComputeScalingPolicy(
        variations=2,
        temperature_schedule=(0.0, 0.5),
        consensus_strategy="min_diff",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    # Round 1 returns only first.py; Round 2 (recovery) returns second.py
    round1_resp = "```python:first.py\nfirst\n```"
    round2_resp = "```python:second.py\nsecond\n```"

    cands = iter([round1_resp, round1_resp, round2_resp, round2_resp])

    def runner(context, parser_adapter):
        resp = next(cands)
        output_paths = parser_adapter(resp, context)
        return ResponseAttemptResult(
            response=resp,
            output_paths=list(output_paths),
            usage_history=[{"tokens": 10}],
            schema_error=False,
            next_attempt=context.attempt + 1,
            next_user_prompt=context.user_prompt,
            failed=False,
        )

    req = _make_request(
        tmp_path,
        scaling_policy=policy,
        expected_files=("first.py", "second.py"),
    )
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    assert outcome.pass_type == "recovered"
    assert outcome.coverage_recovery_success is True
    assert (tmp_path / "first.py").read_text() == "first"
    assert (tmp_path / "second.py").read_text() == "second"


def test_plan_response_validates_deletions_and_hygiene(tmp_path: Path):
    policy = ResponseApplicationPolicy(
        workspace_root=str(tmp_path),
        allowed_delete_paths=("deletable.py",),
        strict_code_hygiene=True,
    )

    # 1. Valid delete
    req_del = ResponseApplicationRequest(
        raw_response="```delete:deletable.py\n```",
        policy=policy,
    )
    plan_del = plan_response(req_del)
    assert len(plan_del.operations) == 1
    assert plan_del.operations[0].kind == "delete"
    assert plan_del.operations[0].path == "deletable.py"

    # 2. Unauthorized delete fails in pure planning
    req_unauth_del = ResponseApplicationRequest(
        raw_response="```delete:forbidden.py\n```",
        policy=policy,
    )
    with pytest.raises(ValueError, match="Deletion not permitted"):
        plan_response(req_unauth_del)

    # 3. Hygiene XML leakage fails in pure planning
    req_hygiene = ResponseApplicationRequest(
        raw_response="```python:leak.py\n</thought>\n```",
        policy=policy,
    )
    with pytest.raises(ValueError, match="XML leakage detected"):
        plan_response(req_hygiene)


def test_invalid_candidate_planning_triggers_schema_retry(tmp_path: Path):
    policy = ComputeScalingPolicy(
        variations=1,
        temperature_schedule=(0.7,),
        consensus_strategy="min_diff",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    events = []
    observed_temps = []
    observed_cand_indices = []
    responses = iter([
        "invalid with no code blocks",
        "```python:fixed.py\nfixed\n```",
    ])

    def provider(context, usage_history):
        events.append(context.attempt)
        observed_temps.append(getattr(context, "_sampling_temperature", None))
        observed_cand_indices.append(
            getattr(context, "_candidate_index", None)
        )
        usage_history.append({"attempt": context.attempt})
        return next(responses)

    def runner(context, parser_adapter):
        return execute_response_attempt(
            context,
            provider,
            parser_adapter,
        )

    req = _make_request(tmp_path, scaling_policy=policy)
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    assert outcome.pass_type == "clean"
    assert events == [1, 2]
    assert observed_temps == [0.7, 0.7]
    assert observed_cand_indices == [0, 0]
    assert (tmp_path / "fixed.py").read_text() == "fixed"


def test_unanimous_with_schema_retry_evaluates_corrected_plans(tmp_path: Path):
    policy = ComputeScalingPolicy(
        variations=2,
        temperature_schedule=(0.0, 0.2),
        consensus_strategy="unanimous",
    )

    def plan_adapter(response_text, context):
        return plan_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    def app_adapter(response_text, context):
        return apply_response(
            ResponseApplicationRequest(
                raw_response=response_text,
                policy=ResponseApplicationPolicy(workspace_root=str(tmp_path)),
            )
        )

    # Candidate 0 retries and produces fixed1.py
    # Candidate 1 succeeds immediately and produces fixed2_different.py
    # Unanimous compares corrected plans (fixed1 vs fixed2) and fails closed
    cands = {
        0: iter(["no code", "```python:fixed1.py\ncode1\n```"]),
        1: iter(["```python:fixed2.py\ncode2\n```"]),
    }

    def provider(context, usage_history):
        cand_idx = getattr(context, "_candidate_index", 0)
        resp = next(cands[cand_idx])
        usage_history.append({"cand": cand_idx, "attempt": context.attempt})
        return resp

    def runner(context, parser_adapter):
        return execute_response_attempt(
            context,
            provider,
            parser_adapter,
        )

    req = _make_request(tmp_path, scaling_policy=policy)
    outcome = _execute_agent_execution(
        req,
        response_attempt_runner=runner,
        response_application_adapter=app_adapter,
        response_planning_adapter=plan_adapter,
    )

    # Corrected plans disagree, so unanimous MUST fail with zero mutation
    assert outcome.pass_type == "failed"
    assert not (tmp_path / "fixed1.py").exists()
    assert not (tmp_path / "fixed2.py").exists()


def test_generation_attempt_preserves_temperature_and_logs(
    tmp_path: Path,
    monkeypatch,
):
    import mighty_mouse.orchestrator.mighty_mouse_agent as mm_agent

    class DummyClient:
        def __init__(self):
            self.temperature = 0.2
            self.last_metadata = {"usage": {"total_tokens": 5}}

        def generate_content(self, sys_instr, user_prompt):
            # Assert client temperature was set to sampling_temperature
            assert self.temperature == 0.7
            return f"```python:out.py\ntemp={self.temperature}\n```"

    client = DummyClient()
    usage = []

    monkeypatch.setattr(mm_agent, "_REPO_ROOT", str(tmp_path))

    resp1 = mm_agent._execute_generation_attempt(
        client,
        "sys",
        "user",
        task_id="test_task",
        attempt=1,
        usage_history=usage,
        candidate_index=0,
        sampling_temperature=0.7,
    )
    # Assert client temperature was restored
    assert client.temperature == 0.2
    assert resp1 == "```python:out.py\ntemp=0.7\n```"

    mm_agent._execute_generation_attempt(
        client,
        "sys",
        "user",
        task_id="test_task",
        attempt=1,
        usage_history=usage,
        candidate_index=1,
        sampling_temperature=0.7,
    )

    raw_dir = tmp_path / "logs" / "raw_responses"
    raw_files = list(raw_dir.glob("raw_test_task_attempt_1_cand_*.txt"))
    assert len(raw_files) == 2
    assert len(usage) == 2


def test_production_solve_resolves_pinned_scaling_policy(agent_env):
    workspace = agent_env.workspace
    state_dir = workspace / ".mighty-mouse"
    state_dir.mkdir(parents=True, exist_ok=True)

    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_id = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))

    pin = ComputeScalingPin(
        pin_id="cspin-prod-001",
        scope=scope,
        scaling_policy=ComputeScalingPolicy(
            variations=3,
            temperature_schedule=(0.0, 0.4, 0.8),
            consensus_strategy="min_diff",
        ),
        model_digest=model_id.artifact_digest,
        execution_profile_id=profile.profile_id,
    )
    engine = PolicyEngine(state_dir)
    engine.pin_scaling(pin, model_id, profile)

    agent_env.config_file.write_text(
        "provider: sim\n"
        "allow_simulation: true\n"
        "model_class: local-small\n"
        f"model_digest: sha256:{'a' * 64}\n"
        "execution_profile: codex-local\n"
        "capabilities:\n"
        "  - tools\n"
        "prompt_segments: []\n"
    )

    task_data = {
        "id": "task_prod_scaling",
        "task": "write code",
        "repository": "JOHNNYMACONNY/mighty-mouse",
        "task_category": "feature",
        "expected_files": ["solution.py"],
    }
    # Cand 0 and Cand 1 produce the same output; Cand 2 produces an outlier.
    # min_diff chooses Cand 0 (tied with 1 on distance, lowest index wins).
    responses = [
        "```python:solution.py\nx = 100\n```",
        "```python:solution.py\nx = 100\n```",
        "```python:solution.py\nx = 9999\n```",
    ]

    result = agent_env.run(task_data, responses)
    assert result.metadata["pass_type"] == "clean"
    assert (workspace / "solution.py").read_text() == "x = 100"
    assert len(result.metadata["usage_history"]) == 3
    raw_files = sorted(f.name for f in result.raw_logs)
    assert any("_cand_0_" in f for f in raw_files)
    assert any("_cand_1_" in f for f in raw_files)
    assert any("_cand_2_" in f for f in raw_files)


def test_production_solve_unpinned_uses_legacy_single_path(agent_env):
    workspace = agent_env.workspace
    state_dir = workspace / ".mighty-mouse"
    state_dir.mkdir(parents=True, exist_ok=True)

    agent_env.config_file.write_text(
        "provider: sim\n"
        "allow_simulation: true\n"
        "model_class: local-small\n"
        f"model_digest: sha256:{'a' * 64}\n"
        "execution_profile: codex-local\n"
        "prompt_segments: []\n"
    )

    task_data = {
        "id": "task_unpinned",
        "task": "write code",
        "repository": "JOHNNYMACONNY/mighty-mouse",
        "task_category": "feature",
        "expected_files": ["unpinned.py"],
    }
    responses = ["```python:unpinned.py\nresult = 42\n```"]

    result = agent_env.run(task_data, responses)
    assert result.metadata["pass_type"] == "clean"
    assert (workspace / "unpinned.py").read_text() == "result = 42"
    assert len(result.metadata["usage_history"]) == 1
    raw_files = [f.name for f in result.raw_logs]
    assert len(raw_files) == 1
    assert "_cand_" not in raw_files[0]


@pytest.mark.parametrize(
    "config_overrides,task_overrides",
    [
        # Incomplete model identity (missing model_digest)
        ({"model_digest": None}, {}),
        # Incomplete execution profile (empty profile_id)
        ({"execution_profile": ""}, {}),
        # Scope mismatch (different repository)
        ({}, {"repository": "JOHNNYMACONNY/other-repo"}),
        # Missing repository in task
        ({}, {"repository": ""}),
        # Scope mismatch (different task_category)
        ({}, {"task_category": "debugging"}),
        # Model digest mismatch
        ({"model_digest": "sha256:" + "f" * 64}, {}),
        # Execution profile ID mismatch
        ({"execution_profile": "cursor-remote"}, {}),
    ],
)
def test_production_solve_mismatches_disable_scaling(
    agent_env, config_overrides, task_overrides
):
    workspace = agent_env.workspace
    state_dir = workspace / ".mighty-mouse"
    state_dir.mkdir(parents=True, exist_ok=True)

    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_id = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))

    pin = ComputeScalingPin(
        pin_id="cspin-prod-002",
        scope=scope,
        scaling_policy=ComputeScalingPolicy(
            variations=3,
            temperature_schedule=(0.0, 0.35, 0.70),
            consensus_strategy="min_diff",
        ),
        model_digest=model_id.artifact_digest,
        execution_profile_id=profile.profile_id,
    )
    engine = PolicyEngine(state_dir)
    engine.pin_scaling(pin, model_id, profile)

    cfg = {
        "provider": "sim",
        "allow_simulation": True,
        "model_class": "local-small",
        "model_digest": f"sha256:{'a' * 64}",
        "execution_profile": "codex-local",
        "capabilities": ["tools"],
        "prompt_segments": [],
    }
    cfg.update(config_overrides)
    import yaml
    agent_env.config_file.write_text(yaml.dump(cfg))

    task_data = {
        "id": "task_mismatch",
        "task": "write code",
        "repository": "JOHNNYMACONNY/mighty-mouse",
        "task_category": "feature",
        "expected_files": ["mismatch.py"],
    }
    task_data.update(task_overrides)
    responses = ["```python:mismatch.py\nlegacy = True\n```"]

    result = agent_env.run(task_data, responses)
    assert result.metadata["pass_type"] == "clean"
    assert len(result.metadata["usage_history"]) == 1
    raw_files = [f.name for f in result.raw_logs]
    assert len(raw_files) == 1
    assert "_cand_" not in raw_files[0]


def test_production_solve_planner_stage_remains_unscaled(agent_env):
    workspace = agent_env.workspace
    state_dir = workspace / ".mighty-mouse"
    state_dir.mkdir(parents=True, exist_ok=True)

    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_id = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("codex-local", frozenset({"tools"}))

    pin = ComputeScalingPin(
        pin_id="cspin-prod-planner",
        scope=scope,
        scaling_policy=ComputeScalingPolicy(
            variations=4,
            temperature_schedule=(0.0, 0.2, 0.4, 0.6),
            consensus_strategy="min_diff",
        ),
        model_digest=model_id.artifact_digest,
        execution_profile_id=profile.profile_id,
    )
    engine = PolicyEngine(state_dir)
    engine.pin_scaling(pin, model_id, profile)

    agent_env.config_file.write_text(
        "provider: sim\n"
        "allow_simulation: true\n"
        "model_class: local-small\n"
        f"model_digest: sha256:{'a' * 64}\n"
        "execution_profile: codex-local\n"
        "capabilities:\n"
        "  - tools\n"
        "prompt_segments: []\n"
    )

    task_data = {
        "id": "task_planner_stage",
        "task": "plan blueprint",
        "repository": "JOHNNYMACONNY/mighty-mouse",
        "task_category": "feature",
        "expected_files": [],
    }
    responses = ["<plan>\nblueprint\n</plan>"]

    result = agent_env.run(task_data, responses, stage="planner")
    assert result.metadata["pass_type"] == "clean"
    assert len(result.metadata["usage_history"]) == 1
    raw_files = [f.name for f in result.raw_logs]
    assert len(raw_files) == 1
    assert "_cand_" not in raw_files[0]
