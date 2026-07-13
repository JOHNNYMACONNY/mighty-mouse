"""CLI adapter for privacy-safe v2 Signal collection and aggregate history."""

from __future__ import annotations

import json

from mighty_mouse.v2.foundation import Mode, Scope, Signal, TaskCategory
from mighty_mouse.v2.signals import SignalLifecycle


def run_signals(
    *, action: str, state_dir: str, signal_id: str | None, repository: str | None,
    mode: str | None, task_category: str | None, model_class: str | None,
    model_digest: str | None, execution_profile: str | None, outcome: str | None,
    duration_ms: int | None, retry_count: int | None, verifier_category: str | None,
    verifier_result: str | None, rating: int | None, json_output: bool,
) -> None:
    lifecycle = SignalLifecycle(state_dir)
    if action == "pause":
        lifecycle.pause()
        document = {"interface": "signals", "action": action, "collection_paused": True}
    elif action == "resume":
        lifecycle.resume()
        document = {"interface": "signals", "action": action, "collection_paused": False}
    elif action == "history":
        document = {"interface": "signals", "history": lifecycle.history()}
    elif action == "purge":
        document = {"interface": "signals", "action": action, "removed_receipts": lifecycle.purge()}
    else:
        required = {
            "signal_id": signal_id, "repository": repository, "mode": mode,
            "task_category": task_category, "model_class": model_class, "model_digest": model_digest,
            "execution_profile": execution_profile, "outcome": outcome, "duration_ms": duration_ms,
            "retry_count": retry_count, "verifier_category": verifier_category, "verifier_result": verifier_result,
        }
        missing = [name for name, value in required.items() if value is None]
        if missing:
            raise ValueError(f"Signal collection requires: {', '.join(missing)}")
        signal = Signal(
            signal_id=signal_id, scope=Scope(Mode(mode), repository, TaskCategory(task_category), model_class),
            model_digest=model_digest, execution_profile_id=execution_profile, outcome=outcome,
            duration_ms=duration_ms, retry_count=retry_count, verifier_category=verifier_category,
            verifier_result=verifier_result, rating=rating,
        )
        receipt_hash = lifecycle.collect(signal)
        document = {"interface": "signals", "action": "collect", "collected": receipt_hash is not None}

    if json_output:
        print(json.dumps(document, sort_keys=True))
        return
    if "history" in document:
        print(f"Collection paused: {document['history']['collection_paused']}")
        print(f"Detailed receipts: {document['history']['receipt_count']}")
        print(f"Aggregate buckets: {len(document['history']['aggregates'])}")
    else:
        print(json.dumps(document, sort_keys=True))
