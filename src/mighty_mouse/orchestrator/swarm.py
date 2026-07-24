"""
Multi-Agent Swarm Orchestrator for Mighty Mouse.
Decomposes execution into specialized subagents: SwarmPlanner, SwarmCoder, and SwarmReviewer.
Supports both Sequential (concurrency=1) and Concurrent Dual-Slot (concurrency=2) execution modes.
"""

import json
import os
import re
import sys
import time
from typing import Dict, List, Optional, Tuple, Any

from ollama_client import OllamaClient
from response_parser import ResponseParser

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


class SwarmCoder:
    def __init__(self, ollama_client: Optional[Any] = None):
        self.ollama_client = ollama_client or OllamaClient()
        self.prompt_segment = _read_prompt_segment("coder")
        self.parser = ResponseParser()

    def code(self, task_data: Dict[str, Any], plan_info: Dict[str, Any], reviewer_feedback: Optional[str] = None, temperature: float = 0.0, workspace_root: Optional[str] = None) -> Dict[str, Any]:
        task_id = task_data.get("id", "unknown_task")
        instruction = task_data.get("instruction", "")
        plan_text = plan_info.get("plan_text", "")

        feedback_str = ""
        if reviewer_feedback:
            feedback_str = f"\n\nREVIEWER FEEDBACK FROM PREVIOUS ATTEMPT:\n{reviewer_feedback}\n"

        user_prompt = (
            f"TASK ID: {task_id}\n\n"
            f"APPROVED ARCHITECTURAL PLAN:\n{plan_text}\n"
            f"{feedback_str}\n"
            f"INSTRUCTION:\n{instruction}\n\n"
            "Please output your surgical file modifications wrapped in <act> tags."
        )

        system_prompt = self.prompt_segment or "You are the Swarm Coder. Write surgical code modifications wrapped in <act>."
        response_text = _llm_generate(self.ollama_client, user_prompt, system_prompt=system_prompt, temperature=temperature)

        # Parse file blocks from response
        file_blocks = re.findall(r"\[FILE:\s*([^\n\]]+)\]\s*```(?:\w+)?\n(.*?)```", response_text, re.DOTALL)
        file_updates = {}
        for file_path, content in file_blocks:
            file_updates[file_path.strip()] = content

        warnings = []
        if not file_updates:
            # Fallback parse via ResponseParser if available
            try:
                written = self.parser.parse_and_write(response_text, workspace_root=workspace_root or ".")
                if isinstance(written, list):
                    for w in written:
                        file_updates[w] = "written"
            except Exception as e:
                warnings.append(f"Parsing warning: {e}")

        return {
            "file_updates": file_updates,
            "warnings": warnings,
            "raw_response": response_text
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
        verifier_func=None
    ) -> Dict[str, Any]:
        """
        Executes the Planner -> Coder -> Reviewer swarm pipeline.
        Supports temperature annealing across retries and optional dual-slot (concurrency=2) candidate generation.
        """
        start_time = time.time()
        temperatures = [0.0, 0.35, 0.70]

        # Stage 1: Architectural Planning
        print(f"[SwarmOrchestrator] Step 1: Running SwarmPlanner (Concurrency={self.concurrency})...", file=sys.stderr)
        plan_result = self.planner.plan(task_data, temperature=0.0)
        print(f"[SwarmOrchestrator] Plan generated. Authorized files: {plan_result.get('authorized_files', [])}", file=sys.stderr)

        reviewer_feedback = None
        best_candidate = None

        for turn in range(max_retries):
            temp = temperatures[min(turn, len(temperatures) - 1)]
            print(f"[SwarmOrchestrator] Step 2: Running SwarmCoder (Turn {turn+1}/{max_retries}, T={temp})...", file=sys.stderr)

            # Support dual-slot (concurrency=2) candidate generation if requested
            candidates = []
            num_slots = self.concurrency if self.concurrency in (1, 2) else 1

            for slot in range(num_slots):
                slot_temp = temp if slot == 0 else min(temp + 0.15, 0.70)
                coder_res = self.coder.code(task_data, plan_result, reviewer_feedback=reviewer_feedback, temperature=slot_temp)
                candidates.append(coder_res)

            # Pick primary candidate (or rank by fewest warnings)
            coder_result = min(candidates, key=lambda c: len(c.get("warnings", [])))

            # Apply surgical changes if verifier_func provided
            verification_result = {"status": "success", "scope": "PASS", "adherence": "PASS", "test_logs": ""}
            if verifier_func:
                verification_result = verifier_func(task_data, coder_result)

            # Stage 3: Independent Review
            review_result = self.reviewer.review(verification_result)
            print(f"[SwarmOrchestrator] Step 3: SwarmReviewer Verdict: {review_result['verdict']}", file=sys.stderr)

            best_candidate = {
                "turn": turn + 1,
                "plan": plan_result,
                "coder": coder_result,
                "review": review_result,
                "verification": verification_result,
                "elapsed_sec": round(time.time() - start_time, 2)
            }

            if review_result["verdict"] == "PASS":
                print(f"[SwarmOrchestrator] Pipeline SUCCEEDED on Turn {turn+1}!", file=sys.stderr)
                break

            reviewer_feedback = review_result["feedback"]
            print(f"[SwarmOrchestrator] Reviewer feedback recorded for retry turn {turn+2}.", file=sys.stderr)

        return best_candidate or {
            "turn": max_retries,
            "plan": plan_result,
            "coder": {},
            "review": {"verdict": "REJECT", "reason": "Max retries reached"},
            "verification": {"status": "failed"},
            "elapsed_sec": round(time.time() - start_time, 2)
        }
