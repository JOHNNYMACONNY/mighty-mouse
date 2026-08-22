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
from typing import Callable, Dict, List, Optional, Sequence, Any

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
        plan_response,
    )
except ImportError:
    from response_application import (
        PlannedOperation,
        ResponseApplicationPolicy,
        ResponseApplicationRequest,
        ResponsePlan,
        plan_response,
    )

# Narrow typed application adapter: receives the selected candidate's
# canonicalized response and returns applied output paths.
# Must already be bound to the intended ResponseApplicationPolicy.
ResponseApplicationAdapter = Callable[[str], Sequence[str]]

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

        try:
            plan = plan_response(
                ResponseApplicationRequest(
                    raw_response=canonical_response,
                    policy=ResponseApplicationPolicy(
                        workspace_root=workspace_root or ".",
                        allowed_delete_paths=tuple(
                            allowed_delete_paths
                        ),
                    ),
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

    def review(self, verification_result: Dict[str, Any], diff_summary: str = "") -> Dict[str, Any]:
        status = verification_result.get("status", "failed")
        scope = verification_result.get("scope", "FAIL")
        adherence = verification_result.get("adherence", "FAIL")
        test_logs = verification_result.get("test_logs", "")
        reason = verification_result.get("reason", "")

        # Automated deterministic review first
        if status == "success" and scope == "PASS" and adherence == "PASS":
            return {
                "verdict": "PASS",
                "reason": "All tests passed cleanly and zero scope violations detected.",
                "feedback": ""
            }

        feedback_parts = []
        if scope != "PASS":
            feedback_parts.append(f"SCOPE VIOLATION: {reason}")
        if adherence != "PASS":
            adh_logs = verification_result.get("adherence_logs", "")
            if adh_logs:
                feedback_parts.append(f"ADHERENCE VIOLATION:\n{adh_logs[:300]}")
        if test_logs and status != "success":
            lines = test_logs.strip().split("\n")
            feedback_parts.append(f"TEST FAILURE:\n" + "\n".join(lines[-20:])[:800])

        feedback_str = "\n".join(feedback_parts) if feedback_parts else reason or "Verification failed."

        return {
            "verdict": "REJECT",
            "reason": f"Verification failed (scope={scope}, status={status}).",
            "feedback": feedback_str
        }


class SwarmOrchestrator:
    def __init__(self, model_name: str = "gemma4:e4b", concurrency: int = 1, ollama_client: Optional[Any] = None):
        self.model_name = model_name
        self.concurrency = concurrency
        self.ollama_client = ollama_client or OllamaClient(config={"model": model_name})
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
    ) -> Dict[str, Any]:
        """Execute the Planner -> Coder -> Reviewer swarm pipeline.

        Supports temperature annealing across retries and optional
        dual-slot (concurrency=2) candidate generation.

        ``application_adapter`` is an opt-in, bound callable that
        accepts the selected winner's canonicalized response text and
        returns the applied output paths.  When omitted, the pipeline
        remains strictly non-mutating (Ticket 1 invariant).

        ``allowed_delete_paths`` is forwarded to SwarmCoder's planning
        policy so that authorized delete operations can be planned at
        the coder stage.  Defaults to empty (no deletes authorized).

        Application is triggered exactly once, only after the reviewer
        returns PASS, and only for the single selected winner candidate.
        Losing candidates and reviewer-rejected candidates are never
        applied.  Application errors fail visibly; no silent swallow
        and no automatic retry.
        """
        start_time = time.time()
        temperatures = [0.0, 0.35, 0.70]

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
                    allowed_delete_paths=allowed_delete_paths,
                )
                candidates.append(coder_res)

            # Select winner by fewest planning/validation warnings
            coder_result = min(
                candidates, key=lambda c: len(c.get("warnings", []))
            )

            # Verifier runs before reviewer (separate seam from application)
            verification_result = {
                "status": "success",
                "scope": "PASS",
                "adherence": "PASS",
                "test_logs": "",
            }
            if verifier_func:
                verification_result = verifier_func(task_data, coder_result)

            # Stage 3: Independent Review
            review_result = self.reviewer.review(verification_result)
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
                "verification": verification_result,
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
                        # Fail-closed: application errors propagate
                        applied_paths = application_adapter(canonical)
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
                "verification": {"status": "failed"},
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
