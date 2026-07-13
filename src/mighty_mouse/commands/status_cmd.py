"""Read-only CLI rendering for the current v2 Effective Policy."""

import json

from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    ImmutableStateStore,
    Mode,
    Scope,
    TaskCategory,
    resolve_model_identity,
    status_document,
)


def run_status(
    *,
    state_dir: str,
    mode: str,
    repository: str,
    task_category: str,
    model_class: str,
    model_digest: str | None,
    model_artifact: str | None,
    execution_profile: str,
    capabilities: list[str] | None,
    json_output: bool,
) -> None:
    document = status_document(
        state_dir=state_dir,
        scope=Scope(
            mode=Mode(mode),
            repository=repository,
            task_category=TaskCategory(task_category),
            model_class=model_class,
        ),
        model_identity=resolve_model_identity(
            artifact_path=model_artifact,
            artifact_digest=model_digest,
        ),
        execution_profile=ExecutionProfile(
            profile_id=execution_profile,
            capabilities=frozenset(capabilities or []),
        ),
    )
    if json_output:
        print(json.dumps(document, sort_keys=True))
        return

    selection = document["selection"]
    print(f"Selected Mode: {document['scope']['mode']}")
    print("Mode override: pass --mode coding, --mode agentic, or --mode hybrid")
    label = "Project improvement" if selection["source"] == "project_improvement" else "Safe starting settings"
    print(f"Effective Policy: {label} ({selection['policy_id']})")
    print(f"Reason: {selection['reason']}")
    print(f"State record: {selection['record_pointer'] or ImmutableStateStore(state_dir).path}")
