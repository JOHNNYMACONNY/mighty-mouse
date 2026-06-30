from __future__ import annotations

import json

from mighty_mouse.protocols import get_protocol


VERIFICATION_REMINDER = (
    "After editing, run Mighty Mouse verification, fix failures, and retry for no more than three rounds."
)


def protocol_document(task_description: str, complexity: str) -> dict:
    return {
        "schema_version": 1,
        "interface": "protocol",
        "task_description": task_description,
        "complexity": complexity,
        "protocol_prompt": get_protocol(complexity),
        "verification_reminder": VERIFICATION_REMINDER,
    }


def run_protocol(task_description: str, complexity: str = "medium", json_output: bool = False) -> None:
    document = protocol_document(task_description, complexity)
    if json_output:
        print(json.dumps(document))
        return

    print(f"Task: {task_description}")
    print(f"Complexity: {complexity}")
    print("\nSelected protocol:\n")
    print(document["protocol_prompt"].rstrip())
    print(f"\nVerification reminder: {document['verification_reminder']}")
