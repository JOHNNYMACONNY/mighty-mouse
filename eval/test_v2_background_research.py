import json

import pytest

from mighty_mouse import cli
from mighty_mouse.v2.foundation import Candidate, Champion, ExecutionProfile, ImmutableStateStore, Mode, ModelIdentity, Policy, Scope, TaskCategory
from mighty_mouse.v2.research import BackgroundResearch, ResearchLimits


def _scope():
    return Scope(Mode.CODING, "JOHNNYMACONNY/mighty-mouse", TaskCategory.FEATURE, "local-small")


def _controller(tmp_path):
    store = ImmutableStateStore(tmp_path)
    candidate = Candidate("candidate-base", Policy("policy-base", Mode.CODING, "1"), _scope(), "sha256:model", frozenset({"tools"}), frozenset({"codex-local"}))
    store.append_candidate(candidate)
    store.append_champion(Champion("champion-base", candidate.candidate_id, _scope(), "sha256:model", "codex-local"))
    return BackgroundResearch(tmp_path)


def _start(controller, protected_task_categories=()):
    return controller.start(
        scope=_scope(), model_identity=ModelIdentity("sha256:model"), execution_profile=ExecutionProfile("codex-local", frozenset({"tools"})),
        protocol_version="v2", limits=ResearchLimits(1, 2, 10, 2, 2), seed_schedule=(7,), task_order=("dev-001",), mutation_paths=("policy",),
        protected_task_categories=protected_task_categories,
    )


def test_background_research_start_freezes_manifest_and_stop_is_sticky(tmp_path):
    controller = _controller(tmp_path)
    started = _start(controller)
    manifest_path = tmp_path / controller.manifest_directory / f"{started['generation_id']}.json"
    before = manifest_path.read_bytes()

    stopped = controller.stop()

    assert started["state"] == "running"
    assert stopped["state"] == "stopped"
    assert controller.status()["state"] == "stopped"
    assert manifest_path.read_bytes() == before
    with pytest.raises(ValueError, match="stopped"):
        controller.run(thermal_state="normal")


def test_background_research_denies_resources_and_invalid_mutations_fail_closed(tmp_path):
    controller = _controller(tmp_path)
    with pytest.raises(ValueError, match="mutation surface"):
        controller.start(
            scope=_scope(), model_identity=ModelIdentity("sha256:model"), execution_profile=ExecutionProfile("codex-local", frozenset({"tools"})),
            protocol_version="v2", limits=ResearchLimits(1, 1, 1, 1, 1), seed_schedule=(7,), task_order=("dev-001",), mutation_paths=("src/mighty_mouse/v2/research.py",),
        )

    _start(controller)
    with pytest.raises(ValueError, match="thermal"):
        controller.run(thermal_state="critical")
    assert controller.status()["state"] == "budget-blocked"
    assert controller.run(thermal_state="normal")["state"] == "completed"


def test_background_research_completion_records_candidate_experiment_and_generation(tmp_path):
    controller = _controller(tmp_path)
    generation_id = _start(controller)["generation_id"]

    completed = controller.run(thermal_state="normal")
    records = ImmutableStateStore(tmp_path).records()
    record_types = {type(record.value).__name__ for record in records}

    assert completed["state"] == "completed"
    assert {"Candidate", "Experiment", "Generation", "EvidenceBundle"}.issubset(record_types)
    generation = next(record.value for record in records if type(record.value).__name__ == "Generation")
    assert generation.generation_id == generation_id
    assert generation.base_champion_id == "champion-base"


def test_research_cli_reports_status_and_keeps_manifest_json(monkeypatch, tmp_path, capsys):
    _controller(tmp_path)
    args = [
        "mighty-mouse", "research", "start", "--state-dir", str(tmp_path), "--repository", "JOHNNYMACONNY/mighty-mouse",
        "--task-category", "feature", "--model-class", "local-small", "--model-digest", "sha256:model",
        "--execution-profile", "codex-local", "--capability", "tools", "--seed", "7", "--task", "dev-001",
        "--mutation-path", "policy", "--json",
    ]
    monkeypatch.setattr("sys.argv", args)
    cli.main()

    document = json.loads(capsys.readouterr().out)
    assert document["interface"] == "background_research"
    assert document["state"] == "running"


def test_research_cli_exercises_stop_denial_mutation_rejection_and_completion(monkeypatch, tmp_path, capsys):
    _controller(tmp_path)

    def run(*arguments):
        monkeypatch.setattr("sys.argv", ["mighty-mouse", "research", *arguments, "--json"])
        cli.main()
        return json.loads(capsys.readouterr().out)

    start = ("start", "--state-dir", str(tmp_path), "--repository", "JOHNNYMACONNY/mighty-mouse", "--task-category", "feature", "--model-class", "local-small", "--model-digest", "sha256:model", "--execution-profile", "codex-local", "--capability", "tools", "--seed", "7", "--task", "dev-001", "--mutation-path", "policy")
    assert run(*start)["state"] == "running"
    assert run("stop", "--state-dir", str(tmp_path))["state"] == "stopped"
    with pytest.raises(ValueError, match="mutation surface"):
        run(*start[:-1], "src/mighty_mouse/cli.py")
    assert run(*start)["state"] == "running"
    with pytest.raises(ValueError, match="thermal"):
        run("run", "--state-dir", str(tmp_path), "--thermal-state", "critical")
    assert run("run", "--state-dir", str(tmp_path))["state"] == "completed"
