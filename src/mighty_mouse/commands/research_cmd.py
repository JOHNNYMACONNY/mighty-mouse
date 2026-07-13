"""CLI adapter for the canonical v2 Background Research controller."""

from __future__ import annotations

import json

from mighty_mouse.v2.foundation import ExecutionProfile, Mode, ModelIdentity, Scope, TaskCategory
from mighty_mouse.v2.research import BackgroundResearch, ResearchLimits


def run_research(*, action: str, state_dir: str, repository: str | None, mode: str, task_category: str, model_class: str | None, model_digest: str | None, execution_profile: str, capabilities: list[str] | None, protocol_version: str, candidate_cap: int, max_tool_calls: int, max_duration_ms: int, max_cost_units: int, max_calls_per_minute: int, seed: list[int] | None, task: list[str] | None, mutation_path: list[str] | None, thermal_state: str, requested_tool_calls: int, requested_duration_ms: int, requested_cost_units: int, json_output: bool) -> None:
    controller = BackgroundResearch(state_dir)
    if action == "status":
        document = controller.status()
    elif action == "stop":
        document = controller.stop()
    elif action == "run":
        document = controller.run(thermal_state=thermal_state, requested_tool_calls=requested_tool_calls, requested_duration_ms=requested_duration_ms, requested_cost_units=requested_cost_units)
    else:
        if not repository or not model_class:
            raise ValueError("research start requires repository and model_class")
        document = controller.start(
            scope=Scope(Mode(mode), repository, TaskCategory(task_category), model_class), model_identity=ModelIdentity(model_digest),
            execution_profile=ExecutionProfile(execution_profile, frozenset(capabilities or [])), protocol_version=protocol_version,
            limits=ResearchLimits(candidate_cap, max_tool_calls, max_duration_ms, max_cost_units, max_calls_per_minute),
            seed_schedule=tuple(seed or ()), task_order=tuple(task or ()), mutation_paths=tuple(mutation_path or ()),
        )
    if json_output:
        print(json.dumps(document, sort_keys=True))
    else:
        print(f"Background Research: {document['state']}")
        if document["generation_id"]:
            print(f"Generation: {document['generation_id']}")
        if document.get("last_reason"):
            print(f"Reason: {document['last_reason']}")
