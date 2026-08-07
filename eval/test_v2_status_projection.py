from pathlib import Path

import pytest

from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.records import (
    ExecutionProfile,
    ModelIdentity,
    Mode,
    Scope,
    TaskCategory,
)
from mighty_mouse.v2.status import build_status_document


def test_status_projection_module_matches_policy_engine_document(
    tmp_path: Path,
) -> None:
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_identity = ModelIdentity("sha256:" + "a" * 64)
    execution_profile = ExecutionProfile(
        "codex-local", frozenset({"test"})
    )
    engine = PolicyEngine(tmp_path)

    document = build_status_document(
        tmp_path,
        scope,
        model_identity,
        execution_profile,
        engine,
    )

    assert document == engine.get_status(
        scope, model_identity, execution_profile
    )
    assert list(document) == [
        "schema_version",
        "interface",
        "scope",
        "model_identity",
        "execution_profile",
        "selection",
        "routing",
        "champion",
        "eligible_successors",
        "history",
        "signals",
    ]


def test_policy_engine_status_delegates_to_canonical_projection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    scope = Scope(
        Mode.CODING,
        "JOHNNYMACONNY/mighty-mouse",
        TaskCategory.FEATURE,
        "local-small",
    )
    model_identity = ModelIdentity("sha256:" + "a" * 64)
    execution_profile = ExecutionProfile("codex-local", frozenset({"test"}))
    engine = PolicyEngine(tmp_path)
    expected = {"interface": "status", "selection": {"policy_id": "test"}}
    calls = []

    def project_status(
        state_dir, selected_scope, identity, profile, policy_engine
    ):
        calls.append(
            (state_dir, selected_scope, identity, profile, policy_engine)
        )
        return expected

    monkeypatch.setattr(
        "mighty_mouse.v2.status.build_status_document", project_status
    )

    document = engine.get_status(scope, model_identity, execution_profile)

    assert document is expected
    assert calls == [
        (tmp_path, scope, model_identity, execution_profile, engine)
    ]
