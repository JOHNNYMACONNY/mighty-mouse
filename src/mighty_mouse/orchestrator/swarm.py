"""
Multi-Agent Swarm Orchestrator for Mighty Mouse.
Decomposes execution into specialized subagents:
SwarmPlanner, SwarmCoder, and SwarmReviewer.
Supports Sequential (concurrency=1) and Concurrent
Dual-Slot (concurrency=2) execution modes.
"""

import json
import os
import re
import sys
import time
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Sequence,
    Tuple,
    Union,
)

try:
    from mighty_mouse.orchestrator.ollama_client import OllamaClient
except ImportError:
    from ollama_client import OllamaClient

try:
    from mighty_mouse.orchestrator.response_application import (
        PlannedOperation,
        ResponseApplicationPolicy,
        ResponseApplicationRequest,
        ResponsePlan,
        apply_response,
        plan_response,
    )
except ImportError:
    from response_application import (
        PlannedOperation,
        ResponseApplicationPolicy,
        ResponseApplicationRequest,
        ResponsePlan,
        apply_response,
        plan_response,
    )

try:
    from mighty_mouse.verifier import (
        CheckResult,
        VerificationResult,
        verify,
    )
except ImportError:
    from verifier import (  # noqa: F401
        CheckResult,
        VerificationResult,
        verify,
    )

# Narrow typed application adapter: receives the authoritative
# ResponseApplicationRequest (with canonical raw response and
# effective policy) and returns applied output paths.
ResponseApplicationAdapter = Callable[
    [ResponseApplicationRequest], Sequence[str]
]


@dataclass(frozen=True)
class SwarmVerificationRequest:
    """Authoritative context supplied to a verification adapter."""

    task_data: Dict[str, Any]
    coder_result: Dict[str, Any]
    application_request: ResponseApplicationRequest


SwarmVerificationAdapter = Callable[
    [SwarmVerificationRequest],
    VerificationResult,
]


def create_isolated_verification_adapter(
    isolated_workspace: str,
    test_command: Optional[Union[str, Sequence[str]]] = None,
    lint_command: Optional[Union[str, Sequence[str]]] = None,
    build_command: Optional[Union[str, Sequence[str]]] = None,
    allowed_paths: Optional[List[str]] = None,
    task_config: Optional[Dict[str, Any]] = None,
    timeout_sec: int = 120,
) -> SwarmVerificationAdapter:
    """Create verification adapter executing against an isolated workspace."""
    def _adapter(request: SwarmVerificationRequest) -> VerificationResult:
        real_policy = request.application_request.policy
        # Rebind workspace_root to isolated workspace while preserving
        # allowed_delete_paths, max_file_bytes, system_mode,
        # strict_code_hygiene
        isolated_policy = ResponseApplicationPolicy(
            workspace_root=isolated_workspace,
            allowed_delete_paths=real_policy.allowed_delete_paths,
            max_file_bytes=real_policy.max_file_bytes,
            system_mode=real_policy.system_mode,
            strict_code_hygiene=real_policy.strict_code_hygiene,
        )
        isolated_req = ResponseApplicationRequest(
            raw_response=request.application_request.raw_response,
            policy=isolated_policy,
        )
        apply_response(isolated_req)
        return verify(
            workspace=isolated_workspace,
            test_command=test_command,
            lint_command=lint_command,
            build_command=build_command,
            allowed_paths=allowed_paths,
            task_config=task_config,
            timeout_sec=timeout_sec,
        )

    return _adapter

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
PROMPT_SEGMENTS_DIR = os.path.join(_REPO_ROOT, "configs", "prompt_segments")


def _read_prompt_segment(name: str) -> str:
    path = os.path.join(PROMPT_SEGMENTS_DIR, f"{name}.txt")
    if os.path.exists(path):
        with open(path, "r", encoding="utf8") as f:
            return f.read().strip()
    return ""


def _llm_generate(client: Any, prompt: str, system_prompt: str = "", temperature: float = 0.0) -> str:
    if hasattr(client, "generate_content"):
        return client.generate_content(system_prompt, prompt)
    if hasattr(client, "generate"):
        return client.generate(prompt, system_prompt=system_prompt, temperature=temperature)
    return ""


class SwarmPlanner:
    def __init__(self, ollama_client: Optional[Any] = None):
        self.ollama_client = ollama_client or OllamaClient()
        self.prompt_segment = _read_prompt_segment("planner")

    def plan(self, task_data: Dict[str, Any], temperature: float = 0.0) -> Dict[str, Any]:
        task_id = task_data.get("id", "unknown_task")
        instruction = task_data.get("instruction", "")
        context = task_data.get("context", "")

        user_prompt = (
            f"TASK ID: {task_id}\n\n"
            f"INSTRUCTION:\n{instruction}\n\n"
            f"CONTEXT & FILES:\n{context}\n\n"
            "Please analyze the task and output your <swarm_plan>."
        )

        system_prompt = self.prompt_segment or "You are the Swarm Planner. Create an architectural blueprint wrapped in <swarm_plan>."
        response_text = _llm_generate(self.ollama_client, user_prompt, system_prompt=system_prompt, temperature=temperature)

        # Extract <swarm_plan> block
        plan_match = re.search(r"<swarm_plan>(.*?)</swarm_plan>", response_text, re.DOTALL)
        plan_text = plan_match.group(1).strip() if plan_match else response_text

        # Extract authorized file paths from impact map
        authorized_files = []
        for line in plan_text.split("\n"):
            if "(" in line and ")" in line and ("MODIFY" in line.upper() or "NEW" in line.upper()):
                file_match = re.search(r"(/[\w\.\-/]+|\w+[\w\.\-/]+)", line)
                if file_match:
                    authorized_files.append(file_match.group(1).strip())

        return {
            "plan_text": plan_text,
            "authorized_files": authorized_files,
            "raw_response": response_text
        }


def _canonicalize_swarm_response(raw_text: str) -> str:
    """Translate legacy [FILE: path]```lang to canonical ```lang:path."""
    def _replace_file_tag(match: re.Match) -> str:
        path = match.group(1).strip()
        lang = match.group(2) or ""
        return f"```{lang}:{path}\n"

    return re.sub(
        r"\[FILE:\s*([^\n\]]+)\]\s*```(\w+)?\n",
        _replace_file_tag,
        raw_text,
    )


class SwarmCoder:
    def __init__(self, ollama_client: Optional[Any] = None):
        self.ollama_client = ollama_client or OllamaClient()
        self.prompt_segment = _read_prompt_segment("coder")

    def code(
        self,
        task_data: Dict[str, Any],
        plan_info: Dict[str, Any],
        reviewer_feedback: Optional[str] = None,
        temperature: float = 0.0,
        workspace_root: Optional[str] = None,
        allowed_delete_paths: tuple = (),
        application_policy: Optional[ResponseApplicationPolicy] = None,
    ) -> Dict[str, Any]:
        task_id = task_data.get("id", "unknown_task")
        instruction = task_data.get("instruction", "")
        plan_text = plan_info.get("plan_text", "")

        feedback_str = ""
        if reviewer_feedback:
            feedback_str = (
                f"\n\nREVIEWER FEEDBACK FROM PREVIOUS ATTEMPT:\n"
                f"{reviewer_feedback}\n"
            )

        user_prompt = (
            f"TASK ID: {task_id}\n\n"
            f"APPROVED ARCHITECTURAL PLAN:\n{plan_text}\n"
            f"{feedback_str}\n"
            f"INSTRUCTION:\n{instruction}\n\n"
            "Please output your surgical file modifications wrapped"
            " in <act> tags."
        )

        system_prompt = (
            self.prompt_segment
            or "You are the Swarm Coder. Write surgical code "
            "modifications wrapped in <act>."
        )
        response_text = _llm_generate(
            self.ollama_client,
            user_prompt,
            system_prompt=system_prompt,
            temperature=temperature,
        )

        # Unify legacy [FILE: path] syntax into canonical code block format
        canonical_response = _canonicalize_swarm_response(response_text)

        response_plan: Optional[Dict[str, Any]] = None
        planned_output_paths: List[str] = []
        file_updates: Dict[str, str] = {}
        warnings: List[str] = []

        effective_policy = application_policy or ResponseApplicationPolicy(
            workspace_root=workspace_root or ".",
            allowed_delete_paths=tuple(allowed_delete_paths),
        )

        try:
            plan = plan_response(
                ResponseApplicationRequest(
                    raw_response=canonical_response,
                    policy=effective_policy,
                )
            )
            response_plan = {
                "operations": [
                    {
                        "kind": op.kind,
                        "path": op.path,
                        "content": op.content,
                    }
                    for op in plan.operations
                ],
                "output_paths": list(plan.output_paths),
            }
            planned_output_paths = list(plan.output_paths)
            for op in plan.operations:
                if op.kind == "write":
                    file_updates[op.path] = op.content
                elif op.kind == "delete":
                    file_updates[op.path] = "deleted"
        except Exception as e:
            warnings.append(f"Parsing warning: {e}")

        return {
            "file_updates": file_updates,
            "planned_output_paths": planned_output_paths,
            "response_plan": response_plan,
            "warnings": warnings,
            "raw_response": response_text,
            "canonical_response": canonical_response,
        }


class SwarmReviewer:
    def __init__(self, ollama_client: Optional[Any] = None):
        self.ollama_client = ollama_client or OllamaClient()
        self.prompt_segment = _read_prompt_segment("reviewer")

    def review(
        self,
        verification_result: Union[VerificationResult, Dict[str, Any]],
        diff_summary: str = "",
    ) -> Dict[str, Any]:
        """Review verification evidence and return PASS/REJECT verdict."""
        if isinstance(verification_result, VerificationResult):
            if verification_result.passed:
                return {
                    "verdict": "PASS",
                    "reason": verification_result.summary,
                    "feedback": "",
                }

            feedback_parts = [
                f"VERIFICATION FAILED: {verification_result.summary}"
            ]
            failed_checks = [
                c for c in verification_result.checks if not c.passed
            ]
            for check in failed_checks:
                out = check.output.strip()
                if len(out) > 500:
                    out = out[-500:]
                feedback_parts.append(
                    f"CHECK '{check.name}' FAILED:\n{out}"
                )
            if verification_result.suggestions:
                feedback_parts.append(
                    "SUGGESTIONS:\n"
                    + "\n".join(
                        f"- {s}"
                        for s in verification_result.suggestions[:5]
                    )
                )
            return {
                "verdict": "REJECT",
                "reason": verification_result.summary,
                "feedback": "\n\n".join(feedback_parts),
            }

        # Legacy dict fallback for existing callers / tests
        status = verification_result.get("status", "failed")
        scope = verification_result.get("scope", "FAIL")
        adherence = verification_result.get("adherence", "FAIL")
        test_logs = verification_result.get("test_logs", "")
        reason = verification_result.get("reason", "")

        if status == "success" and scope == "PASS" and adherence == "PASS":
            return {
                "verdict": "PASS",
                "reason": (
                    "All tests passed cleanly and zero scope violations "
                    "detected."
                ),
                "feedback": "",
            }

        feedback_parts = []
        if scope != "PASS":
            feedback_parts.append(f"SCOPE VIOLATION: {reason}")
        if adherence != "PASS":
            adh_logs = verification_result.get("adherence_logs", "")
            if adh_logs:
                feedback_parts.append(
                    f"ADHERENCE VIOLATION:\n{adh_logs[:300]}"
                )
        if test_logs and status != "success":
            lines = test_logs.strip().split("\n")
            feedback_parts.append(
                f"TEST FAILURE:\n" + "\n".join(lines[-20:])[:800]
            )

        feedback_str = (
            "\n".join(feedback_parts)
            if feedback_parts
            else reason or "Verification failed."
        )

        return {
            "verdict": "REJECT",
            "reason": (
                f"Verification failed (scope={scope}, status={status})."
            ),
            "feedback": feedback_str,
        }


class SwarmOrchestrator:
    def __init__(
        self,
        model_name: str = "gemma4:e4b",
        concurrency: int = 1,
        ollama_client: Optional[Any] = None,
    ):
        self.model_name = model_name
        self.concurrency = concurrency
        self.ollama_client = ollama_client or OllamaClient(
            config={"model": model_name}
        )
        self.planner = SwarmPlanner(self.ollama_client)
        self.coder = SwarmCoder(self.ollama_client)
        self.reviewer = SwarmReviewer(self.ollama_client)

    def execute_swarm_pipeline(
        self,
        task_data: Dict[str, Any],
        max_retries: int = 3,
        verifier_func=None,
        application_adapter: Optional[ResponseApplicationAdapter] = None,
        allowed_delete_paths: tuple = (),
        application_policy: Optional[ResponseApplicationPolicy] = None,
        verification_adapter: Optional[SwarmVerificationAdapter] = None,
    ) -> Dict[str, Any]:
        """Execute the Planner -> Coder -> Reviewer swarm pipeline.

        Supports temperature annealing across retries and optional
        dual-slot (concurrency=2) candidate generation.

        ``verification_adapter`` is an opt-in, typed callable that
        receives a SwarmVerificationRequest and returns a canonical
        VerificationResult.

        ``application_adapter`` is an opt-in, bound callable that
        accepts the selected winner's ResponseApplicationRequest and
        returns the applied output paths.

        When application_adapter is provided without a verification
        adapter, the pipeline fails closed without applying changes.
        """
        if verification_adapter is not None and verifier_func is not None:
            raise ValueError(
                "Cannot supply both legacy verifier_func and canonical "
                "verification_adapter."
            )

        start_time = time.time()
        temperatures = [0.0, 0.35, 0.70]

        effective_policy = application_policy or ResponseApplicationPolicy(
            workspace_root=".",
            allowed_delete_paths=tuple(allowed_delete_paths),
        )

        # Stage 1: Architectural Planning
        print(
            f"[SwarmOrchestrator] Step 1: Running SwarmPlanner "
            f"(Concurrency={self.concurrency})...",
            file=sys.stderr,
        )
        plan_result = self.planner.plan(task_data, temperature=0.0)
        print(
            f"[SwarmOrchestrator] Plan generated. Authorized files: "
            f"{plan_result.get('authorized_files', [])}",
            file=sys.stderr,
        )

        reviewer_feedback = None
        best_candidate = None

        for turn in range(max_retries):
            temp = temperatures[min(turn, len(temperatures) - 1)]
            print(
                f"[SwarmOrchestrator] Step 2: Running SwarmCoder "
                f"(Turn {turn+1}/{max_retries}, T={temp})...",
                file=sys.stderr,
            )

            # Dual-slot (concurrency=2) candidate generation — NON-MUTATING
            candidates = []
            num_slots = (
                self.concurrency if self.concurrency in (1, 2) else 1
            )

            for slot in range(num_slots):
                slot_temp = (
                    temp if slot == 0 else min(temp + 0.15, 0.70)
                )
                coder_res = self.coder.code(
                    task_data,
                    plan_result,
                    reviewer_feedback=reviewer_feedback,
                    temperature=slot_temp,
                    application_policy=effective_policy,
                )
                candidates.append(coder_res)

            # Deterministic candidate ranking:
            # 1. Candidates with validated operations first
            # 2. Fewer planning/validation warnings
            # 3. Slot index ascending (stable tie-break)
            def _rank_key(item: Tuple[int, Dict[str, Any]]) -> tuple:
                slot_idx, cand = item
                rplan = cand.get("response_plan")
                has_ops = bool(rplan and rplan.get("operations"))
                return (
                    0 if has_ops else 1,
                    len(cand.get("warnings", [])),
                    slot_idx,
                )

            coder_result = min(
                enumerate(candidates),
                key=_rank_key,
            )[1]

            # Canonical verification for selected winner candidate
            canonical = coder_result.get(
                "canonical_response",
                coder_result.get("raw_response", ""),
            )
            app_request = ResponseApplicationRequest(
                raw_response=canonical,
                policy=effective_policy,
            )

            verification_payload: Union[VerificationResult, Dict[str, Any]]
            verification_metadata: Dict[str, Any]

            if verification_adapter is not None:
                v_req = SwarmVerificationRequest(
                    task_data=task_data,
                    coder_result=coder_result,
                    application_request=app_request,
                )
                v_res = verification_adapter(v_req)
                if not isinstance(v_res, VerificationResult):
                    raise TypeError(
                        "verification_adapter must return "
                        f"VerificationResult, got {type(v_res).__name__}"
                    )
                verification_payload = v_res
                verification_metadata = {
                    "available": True,
                    "occurred": True,
                    "passed": v_res.passed,
                    "result": v_res.to_dict(),
                }
            elif application_adapter is not None:
                # Fail-closed: real application requires canonical
                # verification_adapter. Legacy verifier_func cannot
                # authorize mutation.
                v_res = VerificationResult(
                    passed=False,
                    checks=[],
                    summary=(
                        "No canonical verification adapter supplied for "
                        "application-enabled pipeline."
                    ),
                    warnings=["Missing canonical verification adapter."],
                )
                verification_payload = v_res
                verification_metadata = {
                    "available": False,
                    "occurred": False,
                    "passed": False,
                    "result": v_res.to_dict(),
                }
            elif verifier_func is not None:
                # Legacy verifier_func supported only when application is disabled
                v_res = verifier_func(task_data, coder_result)
                if isinstance(v_res, VerificationResult):
                    verification_payload = v_res
                    verification_metadata = {
                        "available": True,
                        "occurred": True,
                        "passed": v_res.passed,
                        "result": v_res.to_dict(),
                    }
                elif isinstance(v_res, dict):
                    verification_payload = v_res
                    is_pass = (
                        v_res.get("status") == "success"
                        and v_res.get("scope") == "PASS"
                        and v_res.get("adherence") == "PASS"
                    )
                    verification_metadata = {
                        "available": True,
                        "occurred": True,
                        "passed": is_pass,
                        "result": v_res,
                    }
                else:
                    raise TypeError(
                        "verifier_func must return dict or "
                        f"VerificationResult, got {type(v_res).__name__}"
                    )
            else:
                # Non-mutating CLI mode with no adapter
                verification_payload = {
                    "status": "success",
                    "scope": "PASS",
                    "adherence": "PASS",
                    "test_logs": "",
                }
                verification_metadata = {
                    "available": False,
                    "occurred": False,
                    "passed": True,
                    "result": None,
                }

            # Stage 3: Independent Review
            review_result = self.reviewer.review(verification_payload)
            print(
                f"[SwarmOrchestrator] Step 3: SwarmReviewer Verdict: "
                f"{review_result['verdict']}",
                file=sys.stderr,
            )

            best_candidate = {
                "turn": turn + 1,
                "plan": plan_result,
                "coder": coder_result,
                "review": review_result,
                "verification": verification_metadata,
                "elapsed_sec": round(time.time() - start_time, 2),
            }

            if review_result["verdict"] == "PASS":
                print(
                    f"[SwarmOrchestrator] Pipeline SUCCEEDED on "
                    f"Turn {turn+1}!",
                    file=sys.stderr,
                )

                # Winner-only application: strictly after PASS, once.
                application: Dict[str, Any] = {
                    "available": application_adapter is not None,
                    "occurred": False,
                    "applied_output_paths": [],
                }

                if application_adapter is not None:
                    # Only apply if candidate has validated operations
                    # (writes or authorized deletes); skip empty plans.
                    rplan = coder_result.get("response_plan")
                    has_validated_operations = bool(
                        rplan and rplan.get("operations")
                    )
                    if has_validated_operations:
                        # Use stored canonical artifact from coder stage;
                        # avoids a second canonicalization pass.
                        canonical = coder_result.get(
                            "canonical_response",
                            coder_result.get("raw_response", ""),
                        )
                        app_request = ResponseApplicationRequest(
                            raw_response=canonical,
                            policy=effective_policy,
                        )
                        # Fail-closed: application errors propagate
                        applied_paths = application_adapter(app_request)
                        application["occurred"] = True
                        application["applied_output_paths"] = list(
                            applied_paths
                        )
                        print(
                            f"[SwarmOrchestrator] Applied winner to: "
                            f"{application['applied_output_paths']}",
                            file=sys.stderr,
                        )

                best_candidate["application"] = application
                break

            reviewer_feedback = review_result["feedback"]
            print(
                f"[SwarmOrchestrator] Reviewer feedback recorded for "
                f"retry turn {turn+2}.",
                file=sys.stderr,
            )

        if best_candidate is None:
            best_candidate = {
                "turn": max_retries,
                "plan": plan_result,
                "coder": {},
                "review": {
                    "verdict": "REJECT",
                    "reason": "Max retries reached",
                },
                "verification": {
                    "available": False,
                    "occurred": False,
                    "passed": False,
                    "result": None,
                },
                "elapsed_sec": round(time.time() - start_time, 2),
            }

        # Ensure application metadata present on all paths (JSON safe)
        if "application" not in best_candidate:
            best_candidate["application"] = {
                "available": application_adapter is not None,
                "occurred": False,
                "applied_output_paths": [],
            }

        return best_candidate
