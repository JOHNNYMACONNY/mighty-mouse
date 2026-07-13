import json

import pytest

from mighty_mouse import cli
from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    HybridHandoff,
    ImmutableStateStore,
    ModelIdentity,
    Mode,
    Scope,
    TaskCategory,
    status_document,
)
from mighty_mouse.v2.runtime import AutopilotRunRequest, run_autopilot


def test_autopilot_honors_an_explicit_mode_override(tmp_path):
    result = run_autopilot(
        AutopilotRunRequest(
            repository="JOHNNYMACONNY/mighty-mouse",
            task_category=TaskCategory.FEATURE,
            model_class="local-small",
            inferred_mode=Mode.CODING,
            confidence_percent=99,
            model_identity=ModelIdentity(None),
            execution_profile=ExecutionProfile("codex-local", frozenset()),
            user_mode=Mode.AGENTIC,
        ),
        ImmutableStateStore(tmp_path),
    )

    assert result.mode is Mode.AGENTIC
    assert result.routing_reason == "explicit user Mode override"
    assert result.selection.policy.policy_id == "safe-baseline-agentic"
    assert result.routing_record_hash is not None
    document = status_document(
        tmp_path,
        Scope(Mode.AGENTIC, "JOHNNYMACONNY/mighty-mouse", TaskCategory.FEATURE, "local-small"),
        ModelIdentity(None), ExecutionProfile("codex-local", frozenset()),
    )
    assert document["routing"]["reason"] == "explicit user Mode override"
    assert document["routing"]["record_pointer"].endswith(result.routing_record_hash)


def test_autopilot_direct_routes_a_high_confidence_inferred_mode(tmp_path):
    result = run_autopilot(
        AutopilotRunRequest(
            repository="JOHNNYMACONNY/mighty-mouse",
            task_category=TaskCategory.DEBUGGING,
            model_class="local-small",
            inferred_mode=Mode.AGENTIC,
            confidence_percent=80,
            model_identity=ModelIdentity(None),
            execution_profile=ExecutionProfile("codex-local", frozenset()),
        ),
        ImmutableStateStore(tmp_path),
    )

    assert result.mode is Mode.AGENTIC
    assert result.routing_reason == "high-confidence inferred Mode"


def test_autopilot_requires_a_handoff_for_medium_confidence_hybrid_routing(tmp_path):
    request = AutopilotRunRequest(
        repository="JOHNNYMACONNY/mighty-mouse",
        task_category=TaskCategory.FEATURE,
        model_class="local-small",
        inferred_mode=Mode.CODING,
        confidence_percent=79,
        model_identity=ModelIdentity(None),
        execution_profile=ExecutionProfile("codex-local", frozenset()),
    )

    with pytest.raises(ValueError, match="durable Hybrid handoff"):
        run_autopilot(request, ImmutableStateStore(tmp_path))


def test_autopilot_requires_a_handoff_for_an_explicit_hybrid_override(tmp_path):
    request = AutopilotRunRequest(
        repository="JOHNNYMACONNY/mighty-mouse",
        task_category=TaskCategory.FEATURE,
        model_class="local-small",
        inferred_mode=Mode.CODING,
        confidence_percent=99,
        model_identity=ModelIdentity(None),
        execution_profile=ExecutionProfile("codex-local", frozenset()),
        user_mode=Mode.HYBRID,
    )

    with pytest.raises(ValueError, match="durable Hybrid handoff"):
        run_autopilot(request, ImmutableStateStore(tmp_path))


def test_autopilot_requires_user_mode_choice_below_the_confidence_floor(tmp_path):
    request = AutopilotRunRequest(
        repository="JOHNNYMACONNY/mighty-mouse",
        task_category=TaskCategory.FEATURE,
        model_class="local-small",
        inferred_mode=Mode.CODING,
        confidence_percent=54,
        model_identity=ModelIdentity(None),
        execution_profile=ExecutionProfile("codex-local", frozenset()),
    )

    with pytest.raises(ValueError, match="explicit user Mode choice"):
        run_autopilot(request, ImmutableStateStore(tmp_path))


def test_autopilot_persists_a_valid_hybrid_handoff_before_returning(tmp_path):
    scope = Scope(
        mode=Mode.HYBRID,
        repository="JOHNNYMACONNY/mighty-mouse",
        task_category=TaskCategory.FEATURE,
        model_class="local-small",
    )
    handoff = HybridHandoff(
        handoff_id="handoff-001",
        scope=scope,
        summary="Investigate the selected files before coding.",
        constraints=("keep the public interface stable",),
        acceptance_checks=("focused tests pass",),
        file_scope=("src/mighty_mouse/v2",),
        risks=("routing regression",),
    )

    result = run_autopilot(
        AutopilotRunRequest(
            repository=scope.repository,
            task_category=scope.task_category,
            model_class=scope.model_class,
            inferred_mode=Mode.CODING,
            confidence_percent=79,
            model_identity=ModelIdentity(None),
            execution_profile=ExecutionProfile("codex-local", frozenset()),
            hybrid_handoff=handoff,
        ),
        ImmutableStateStore(tmp_path),
    )

    assert result.mode is Mode.HYBRID
    assert result.handoff_record_hash is not None


def test_run_cli_uses_the_autopilot_boundary(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(
        "sys.argv",
        [
            "mighty-mouse",
            "run",
            "--state-dir",
            str(tmp_path),
            "--repository",
            "JOHNNYMACONNY/mighty-mouse",
            "--task-category",
            "feature",
            "--model-class",
            "local-small",
            "--inferred-mode",
            "coding",
            "--confidence-percent",
            "99",
            "--mode",
            "agentic",
            "--execution-profile",
            "codex-local",
            "--json",
        ],
    )

    cli.main()

    document = json.loads(capsys.readouterr().out)
    assert document["interface"] == "run"
    assert document["mode"] == "agentic"
    assert document["routing_reason"] == "explicit user Mode override"


@pytest.mark.parametrize(
    ("confidence_percent", "expected_mode"), [(80, "agentic"), (55, "hybrid")],
)
def test_run_cli_covers_direct_and_hybrid_confidence_boundaries(monkeypatch, tmp_path, capsys, confidence_percent, expected_mode):
    arguments = [
        "mighty-mouse", "run", "--state-dir", str(tmp_path), "--repository", "JOHNNYMACONNY/mighty-mouse",
        "--task-category", "feature", "--model-class", "local-small", "--inferred-mode", "agentic",
        "--confidence-percent", str(confidence_percent), "--execution-profile", "codex-local", "--json",
    ]
    if confidence_percent == 55:
        handoff_path = tmp_path / "handoff.json"
        handoff_path.write_text(json.dumps({"handoff_id": "handoff-001", "summary": "Investigated.", "constraints": [], "acceptance_checks": ["tests"], "file_scope": ["src"], "risks": []}))
        arguments.extend(["--handoff-file", str(handoff_path)])
    monkeypatch.setattr("sys.argv", arguments)

    cli.main()

    assert json.loads(capsys.readouterr().out)["mode"] == expected_mode


def test_run_cli_requires_an_explicit_mode_below_confidence_floor(monkeypatch, tmp_path):
    monkeypatch.setattr("sys.argv", [
        "mighty-mouse", "run", "--state-dir", str(tmp_path), "--repository", "JOHNNYMACONNY/mighty-mouse",
        "--task-category", "feature", "--model-class", "local-small", "--inferred-mode", "coding",
        "--confidence-percent", "54", "--execution-profile", "codex-local", "--json",
    ])

    with pytest.raises(ValueError, match="explicit user Mode choice"):
        cli.main()


def test_status_cli_uses_the_durable_selected_mode(monkeypatch, tmp_path, capsys):
    store = ImmutableStateStore(tmp_path)
    run_autopilot(AutopilotRunRequest(
        repository="JOHNNYMACONNY/mighty-mouse", task_category=TaskCategory.FEATURE, model_class="local-small",
        inferred_mode=Mode.AGENTIC, confidence_percent=80, model_identity=ModelIdentity(None),
        execution_profile=ExecutionProfile("codex-local", frozenset()),
    ), store)
    monkeypatch.setattr("sys.argv", [
        "mighty-mouse", "status", "--state-dir", str(tmp_path), "--mode", "coding",
        "--repository", "JOHNNYMACONNY/mighty-mouse", "--task-category", "feature",
        "--model-class", "local-small", "--execution-profile", "codex-local", "--json",
    ])

    cli.main()

    document = json.loads(capsys.readouterr().out)
    assert document["scope"]["mode"] == "agentic"
    assert document["routing"]["selected_mode"] == "agentic"


def test_run_cli_accepts_a_hybrid_handoff_file(monkeypatch, tmp_path, capsys):
    handoff_path = tmp_path / "handoff.json"
    handoff_path.write_text(json.dumps({
        "handoff_id": "handoff-001",
        "summary": "Investigation completed.",
        "constraints": ["preserve behavior"],
        "acceptance_checks": ["tests pass"],
        "file_scope": ["src/mighty_mouse"],
        "risks": ["regression"],
    }))
    monkeypatch.setattr("sys.argv", [
        "mighty-mouse", "run", "--state-dir", str(tmp_path),
        "--repository", "JOHNNYMACONNY/mighty-mouse", "--task-category", "feature",
        "--model-class", "local-small", "--inferred-mode", "coding",
        "--confidence-percent", "79", "--execution-profile", "codex-local",
        "--handoff-file", str(handoff_path), "--json",
    ])

    cli.main()

    document = json.loads(capsys.readouterr().out)
    assert document["mode"] == "hybrid"
    assert document["handoff_record_hash"]
