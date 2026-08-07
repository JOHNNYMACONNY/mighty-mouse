"""Canonical Policy Mutation Engine for typed Candidate mutations."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Callable, List, Mapping, Optional, Tuple

import yaml

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_EVAL_DIR = os.path.dirname(os.path.abspath(__file__))
if _EVAL_DIR not in sys.path:
    sys.path.append(_EVAL_DIR)
if _REPO_ROOT not in sys.path:
    sys.path.append(_REPO_ROOT)
sys.path.append(
    os.path.join(_REPO_ROOT, "src", "mighty_mouse", "orchestrator")
)

from gemini_client import GeminiClient  # noqa: E402

if TYPE_CHECKING:
    from mighty_mouse.v2.seams import Candidate, VerificationResult


SEGMENTS_DIR = "configs/prompt_segments"
AGENT_CONFIG = "configs/mighty_mouse_v1.yaml"

CATEGORY_TO_SEGMENT = {
    "SCOPE": "constraints.txt",
    "ADHERENCE": "discipline.txt",
    "LOGIC": "reasoning.txt",
    "VERIFICATION": "verification.txt",
    "REGRESSION": "discipline.txt",
    "EFFICIENCY": "reasoning.txt",
    "PARSER": "constraints.txt",
    "TIMEOUT": "timeout_policy",
}


def _allowed_segments(mutation_surface: object) -> frozenset[str] | None:
    if mutation_surface is None:
        return None
    if isinstance(mutation_surface, Mapping):
        return mutation_surface.get("allowed_segments")
    return getattr(mutation_surface, "allowed_segments", None)


@dataclass(frozen=True)
class MutationAttempt:
    segment_file: str
    hypothesis: str
    new_content: str


class PolicyMutationEngine:
    """Apply typed, surface-constrained mutations to immutable Candidates."""

    def __init__(
        self,
        segments_dir: str = SEGMENTS_DIR,
        agent_config: str = AGENT_CONFIG,
        client_factory: Optional[Callable[..., Any]] = None,
    ) -> None:
        self.segments_dir = segments_dir
        self.agent_config = agent_config
        self.client_factory = client_factory or GeminiClient

    def generate_mutation(
        self,
        category: str,
        failures: List[dict[str, Any]],
    ) -> Tuple[Optional[str], Optional[MutationAttempt]]:
        segment_file = CATEGORY_TO_SEGMENT.get(category, "reasoning.txt")
        segment_path = os.path.join(self.segments_dir, segment_file)

        if not os.path.exists(segment_path):
            return segment_file, None

        with open(segment_path, "r") as file:
            current_content = file.read()

        examples = "\n".join(
            f"- Task: {failure['task_id']}, "
            f"Reason: {failure.get('reason', '')}"
            for failure in failures[:3]
        )
        prompt = f"""
You are a Prompt Engineering Expert for the Mighty Mouse project.
We are seeing failures in the category: {category}.
Representative failures:
{examples}

Current content of '{segment_file}':
{current_content}

Your goal is to provide a MINIMAL mutation to this segment to address these
failures without breaking existing behavior.
Output your response in this JSON format:
{{
  "hypothesis": "Your specific hypothesis on why this change will help",
  "new_content": "The full new content for the segment"
}}
"""
        if not os.path.exists(self.agent_config):
            return segment_file, None

        with open(self.agent_config, "r") as file:
            config = yaml.safe_load(file)

        client = self.client_factory(config=config)
        try:
            response_text = client.generate_content(
                "You are a prompt engineering expert.", prompt
            )
            if "```json" in response_text:
                response_text = response_text.split("```json")[1]
                response_text = response_text.split("```")[0].strip()
            elif "{" in response_text:
                response_text = response_text[
                    response_text.find("{"): response_text.rfind("}") + 1
                ]

            mutation_data = json.loads(response_text)
            attempt = MutationAttempt(
                segment_file=segment_file,
                hypothesis=mutation_data.get("hypothesis", ""),
                new_content=mutation_data.get("new_content", ""),
            )
            return segment_file, attempt
        except Exception as exc:
            print(f"[!] Mutation generation failed: {exc}")
            return segment_file, None

    def mutate_candidate(
        self,
        candidate: "Candidate",
        verification: "VerificationResult",
        mutation_surface: Optional[object] = None,
    ) -> "Candidate":
        """Apply typed feedback and return a new immutable Candidate."""
        from mighty_mouse.v2.seams import Candidate as V2Candidate

        policy_data = dict(candidate.policy_data)
        if hasattr(verification, "details"):
            category = str(
                verification.details.get("verifier_category", "LOGIC")
            )
            failures = (
                []
                if verification.passed
                else [
                    {
                        "task_id": candidate.candidate_id,
                        "reason": "typed verification failure",
                    }
                ]
            )
        else:
            category = str(getattr(verification, "verifier_category", "LOGIC"))
            failures = []

        segment_file, attempt = (None, None)
        if failures:
            segment_file, attempt = self.generate_mutation(category, failures)
        if attempt:
            allowed_segments = _allowed_segments(mutation_surface)
            if allowed_segments is None or segment_file in allowed_segments:
                policy_data[segment_file] = attempt.new_content
                policy_data["mutation_hypothesis"] = attempt.hypothesis

        cand_id = f"{candidate.candidate_id}_m"
        return V2Candidate(
            candidate_id=cand_id,
            generation_id=candidate.generation_id,
            mode=candidate.mode,
            policy_data=policy_data,
            status="pending",
        )
