"""Unified Model Execution Engine for Mighty Mouse Orchestrator.

Encapsulates LLM provider client delegation, structured generation, response JSON parsing, and token estimation behind a single deep interface.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from mighty_mouse.orchestrator.gemini_client import GeminiClient
from mighty_mouse.orchestrator.response_parser import ResponseParser

logger = logging.getLogger(__name__)


class ModelExecutionEngine:
    """Deep module orchestrating LLM execution, response parsing, and token estimation."""

    def __init__(self, config: Optional[Dict[str, Any]] = None, client: Optional[Any] = None) -> None:
        self.config = config or {}
        self.client = client if client is not None else GeminiClient(self.config)
        self.parser = ResponseParser()

    def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        require_json: bool = False,
    ) -> Dict[str, Any]:
        """Execute a generation request, returning structured text and metadata."""
        raw_response = self.client.generate_content(system_instruction or "", prompt)
        
        parsed_result = None
        if require_json:
            try:
                import json
                parsed_result = json.loads(raw_response)
            except Exception:
                parsed_result = None
        
        metadata = getattr(self.client, "last_metadata", {})
        
        return {
            "text": raw_response,
            "parsed": parsed_result,
            "metadata": metadata,
        }

    def estimate_tokens(self, text: str) -> int:
        """Estimate token count using 4 chars per token rule of thumb."""
        return len(text) // 4
