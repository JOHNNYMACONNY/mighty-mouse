"""Public protocol command output."""

from __future__ import annotations

import json

from mighty_mouse.protocols import get_protocol

VERIFICATION_REMINDER = (
    "After editing, call mighty-mouse/verify. Fix failures and retry up to three rounds."
)


def protocol_payload(task_description: str, complexity: str) -> dict:
    return {
        "schema_version": 1,
        "interface": "protocol",
        "task_description": task_description.strip(),
        "complexity": complexity,
        "protocol_prompt": get_protocol(complexity=complexity),
        "verification_reminder": VERIFICATION_REMINDER,
    }


def run_protocol(
    task_description: str,
    complexity: str = "medium",
    json_output: bool = False,
) -> None:
    payload = protocol_payload(task_description, complexity)
    if json_output:
        print(json.dumps(payload))
        return

    print(f"Task: {payload['task_description']}")
    print(f"Complexity: {payload['complexity']}")
    print(payload["protocol_prompt"].rstrip())
    print(f"\nVerification reminder: {payload['verification_reminder']}")
