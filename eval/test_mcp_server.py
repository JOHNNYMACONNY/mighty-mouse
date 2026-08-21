import os
import sys
import json
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from mighty_mouse.protocols import get_protocol


MCP_SRC = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "mcp", "src"))
sys.path.insert(0, MCP_SRC)
GEMMA_MODEL = "gemma4:e4b"

try:
    import mcp.client.stdio  # noqa: F401
    mcp_stdio_available = True
except ImportError:
    mcp_stdio_available = False

mcp_available = True


def configure_cline_adapter(workspace: Path, *, model_digest: str, model_class: str = "local-large") -> None:
    from mighty_mouse_mcp.server import _adapter_config

    state_dir = workspace / ".mighty-mouse"
    state_dir.mkdir()
    config = _adapter_config(
        repository="JOHNNYMACONNY/mighty-mouse", model_digest=model_digest,
        model_class=model_class, effective_context_limit=8192,
        runtime_kind="cline", runtime_version="3.54.0", ollama_model=None,
    )
    (state_dir / "mcp-adapter.json").write_text(json.dumps(config), encoding="utf-8")


def write_ollama_manifest(home: Path, model: str, digest: str) -> None:
    name, tag = model.rsplit(":", 1)
    path = home / ".ollama" / "models" / "manifests" / "registry.ollama.ai" / "library" / name / tag
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"layers": [
        {"mediaType": "application/vnd.ollama.image.model", "digest": digest},
    ]}), encoding="utf-8")


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_protocol_depth_scales():
    from mighty_mouse_mcp.server import run_protocol

    low = run_protocol("Change one label", "low")
    high = run_protocol("Refactor persistence", "high")

    assert low["protocol_version"] == "v9.1"
    assert "<scope>" in low["protocol_prompt"]
    assert "12. Search semantic synonyms" in high["protocol_prompt"]
    assert len(high["protocol_prompt"]) > len(low["protocol_prompt"])
    assert "verify_and_record" in low["verification_reminder"]
    assert "verify_and_record" in low["protocol_prompt"]
    assert "verify_and_record" in high["protocol_prompt"]


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_verify_tool_returns_structured_result(tmp_path):
    from mighty_mouse_mcp.server import run_verify

    result = run_verify(
        str(tmp_path),
        test_command=[sys.executable, "-c", "print('ok')"],
    )

    assert result["passed"] is True
    assert result["checks"][0]["name"] == "tests"
    assert result["suggestions"] == []
    assert result["detected_projects"] == []
    assert result["warnings"] == []


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_verify_and_record_collects_a_privacy_safe_signal(tmp_path):
    from mighty_mouse_mcp.server import run_verify_and_record

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "a" * 64)
    result = run_verify_and_record(
        str(tmp_path),
        test_command=[sys.executable, "-c", "print('ok')"],
    )

    assert result["verification"]["passed"] is True
    assert result["signal_recorded"] is True
    assert len(result["receipt_hash"]) == 64
    receipts = list((tmp_path / ".mighty-mouse" / "v2-signal-receipts").glob("*.json"))
    assert len(receipts) == 1
    receipt = json.loads(receipts[0].read_text())
    signal = receipt["signal"]
    assert signal["scope"] == {
        "mode": "coding",
        "repository": "JOHNNYMACONNY/mighty-mouse",
        "task_category": "unknown",
        "model_class": "local-large",
    }
    assert signal["outcome"] == "passed"
    assert signal["verifier_category"] == "tests"
    assert "ok" not in json.dumps(receipt)
    assert str(tmp_path) not in json.dumps(receipt)


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_verify_and_record_preserves_failed_verification(tmp_path):
    from mighty_mouse_mcp.server import run_verify_and_record

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "b" * 64)
    result = run_verify_and_record(
        str(tmp_path),
        test_command=[sys.executable, "-c", "raise SystemExit(1)"],
        retry_count=2,
    )

    assert result["verification"]["passed"] is False
    assert result["signal_recorded"] is True
    receipt = json.loads(next((tmp_path / ".mighty-mouse" / "v2-signal-receipts").glob("*.json")).read_text())
    assert receipt["signal"]["outcome"] == "failed"
    assert receipt["signal"]["retry_count"] == 2


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_verify_and_record_refuses_unconfigured_or_unknown_provenance(tmp_path):
    from mighty_mouse_mcp.server import run_verify_and_record

    with pytest.raises(ValueError, match="not configured"):
        run_verify_and_record(str(tmp_path))
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "e" * 64)
    config = tmp_path / ".mighty-mouse" / "mcp-adapter.json"
    document = json.loads(config.read_text())
    document["execution_profile_id"] = "unknown"
    config.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="stale"):
        run_verify_and_record(str(tmp_path))


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_setup_workspace_pins_ollama_identity_without_manual_json(tmp_path, monkeypatch):
    from mighty_mouse_mcp.server import run_setup_workspace

    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    digest = "sha256:" + "f" * 64
    write_ollama_manifest(home, GEMMA_MODEL, digest)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_setup_workspace(
        str(workspace),
        repository="JOHNNYMACONNY/mighty-mouse",
        ollama_model=GEMMA_MODEL,
        model_class="local-small",
        effective_context_limit=8192,
        runtime_kind="cline",
        runtime_version="3.32.2",
    )

    assert result["configured"] is True
    config = json.loads((workspace / ".mighty-mouse" / "mcp-adapter.json").read_text())
    assert config["model_digest"] == digest
    assert config["execution_profile_id"].startswith("sha256:")
    assert run_setup_workspace(
        str(workspace),
        repository="JOHNNYMACONNY/mighty-mouse",
        ollama_model=GEMMA_MODEL,
        model_class="local-small",
        effective_context_limit=8192,
        runtime_kind="cline",
        runtime_version="3.32.2",
    )["configured"] is False

    with pytest.raises(ValueError, match="runtime kind"):
        run_setup_workspace(
            str(workspace),
            repository="JOHNNYMACONNY/mighty-mouse",
            ollama_model=GEMMA_MODEL,
            model_class="local-small",
            runtime_kind="unknown",
            runtime_version="unknown",
        )

    write_ollama_manifest(home, GEMMA_MODEL, "sha256:" + "b" * 64)
    from mighty_mouse_mcp.server import run_verify_and_record
    with pytest.raises(ValueError, match="model identity changed"):
        run_verify_and_record(str(workspace))


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_setup_workspace_accepts_a_pinned_non_ollama_host_identity(tmp_path):
    from mighty_mouse_mcp.server import run_setup_workspace

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    result = run_setup_workspace(
        str(workspace), repository="JOHNNYMACONNY/mighty-mouse",
        model_digest="sha256:" + "9" * 64, model_class="local-large",
        runtime_kind="codex", runtime_version="1.2.3",
    )

    assert result["configured"] is True
    assert json.loads((workspace / ".mighty-mouse" / "mcp-adapter.json").read_text())["model_digest"] == "sha256:" + "9" * 64


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_setup_partitions_profiles_by_exact_host_facts_and_full_tool_contract(tmp_path):
    from mighty_mouse_mcp.server import _mcp_tool_contract, run_setup_workspace

    first, second = tmp_path / "first", tmp_path / "second"
    first.mkdir()
    second.mkdir()
    shared = {"repository": "JOHNNYMACONNY/mighty-mouse", "model_digest": "sha256:" + "8" * 64, "model_class": "local-large"}
    first_result = run_setup_workspace(str(first), runtime_kind="cline", runtime_version="3.54.0", **shared)
    second_result = run_setup_workspace(str(second), runtime_kind="codex", runtime_version="1.2.3", **shared)

    assert first_result["execution_profile_id"] != second_result["execution_profile_id"]
    assert set(_mcp_tool_contract()) == {
        "contract_version",
        "protocol",
        "verify",
        "setup_workspace",
        "verify_and_record",
        "recording_audit",
        "run",
        "policy_status",
        "policy_preview",
        "policy_pin",
        "policy_rollback",
        "compute_scaling_status",
        "compute_scaling_preview",
        "compute_scaling_pin",
    }


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_recording_requires_reonboarding_after_a_tool_contract_change(tmp_path, monkeypatch):
    import mighty_mouse_mcp.server as server

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "7" * 64)
    monkeypatch.setattr(server, "MCP_TOOL_CONTRACT_VERSION", 5)
    with pytest.raises(ValueError, match="stale"):
        server.run_verify_and_record(str(tmp_path))

    server.run_setup_workspace(
        str(tmp_path), "JOHNNYMACONNY/mighty-mouse", model_digest="sha256:" + "7" * 64,
        model_class="local-large", runtime_kind="cline", runtime_version="3.54.0", replace=True,
    )
    assert server.run_verify_and_record(
        str(tmp_path), test_command=[sys.executable, "-c", "print('ok')"],
    )["signal_recorded"] is True


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_recording_audit_reports_a_signal_after_the_task_started(tmp_path):
    from mighty_mouse_mcp.server import run_recording_audit, run_verify_and_record

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "a" * 64)
    started_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    result = run_verify_and_record(str(tmp_path), test_command=[sys.executable, "-c", "print('ok')"])
    assert run_recording_audit(str(tmp_path), "0" * 64, started_at.isoformat())["recorded"] is False
    audit = run_recording_audit(str(tmp_path), result["receipt_hash"], started_at.isoformat().replace("+00:00", "Z"))
    assert audit == {"recorded": True, "recent_receipt_count": 1}


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_optional_hook_command_fails_closed_when_no_signal_was_recorded(tmp_path):
    from mighty_mouse_mcp.server import run_verify_and_record

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "a" * 64)
    started_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    environment = {**os.environ, "PYTHONPATH": os.pathsep.join([os.path.abspath("src"), MCP_SRC])}
    command = [
        sys.executable, "-m", "mighty_mouse_mcp.hooks", str(tmp_path), "--receipt-hash", "0" * 64,
        "--after", started_at.isoformat(),
    ]
    assert subprocess.run(command, env=environment, capture_output=True, text=True).returncode == 1
    result = run_verify_and_record(str(tmp_path), test_command=[sys.executable, "-c", "print('ok')"])
    command[5] = result["receipt_hash"]
    assert subprocess.run(command, env=environment, capture_output=True, text=True).returncode == 0


def test_unknown_protocol_complexity_is_rejected():
    with pytest.raises(ValueError):
        get_protocol("extreme")


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_uses_pinned_adapter_runtime_context(tmp_path):
    from mighty_mouse_mcp.server import run_run
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "1" * 64, model_class="local-small")

    result = run_run(
        str(tmp_path),
        task_category="feature",
        inferred_mode="coding",
        confidence_percent=100,
    )

    assert result["interface"] == "run"
    assert result["mode"] == "coding"
    assert result["routing_reason"] == "high-confidence inferred Mode"
    assert result["selection"]["policy_id"] == "safe-baseline-coding"
    assert result["routing_record_hash"] is not None


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_matches_direct_autopilot_high_confidence(tmp_path):
    from mighty_mouse_mcp.server import run_run, _adapter_config
    from mighty_mouse.v2.runtime import AutopilotRunRequest, run_autopilot
    from mighty_mouse.v2.foundation import (
        ExecutionProfile,
        ImmutableStateStore,
        ModelIdentity,
        Mode,
        TaskCategory,
    )

    state_dir = tmp_path / ".mighty-mouse"
    state_dir.mkdir()
    config = _adapter_config(
        repository="JOHNNYMACONNY/mighty-mouse",
        model_digest="sha256:" + "2" * 64,
        model_class="local-small",
        effective_context_limit=8192,
        runtime_kind="codex",
        runtime_version="1.2.3",
        ollama_model=None,
    )
    (state_dir / "mcp-adapter.json").write_text(json.dumps(config), encoding="utf-8")

    mcp_result = run_run(
        str(tmp_path),
        task_category="debugging",
        inferred_mode="agentic",
        confidence_percent=85,
    )

    direct_result = run_autopilot(
        AutopilotRunRequest(
            repository="JOHNNYMACONNY/mighty-mouse",
            task_category=TaskCategory.DEBUGGING,
            model_class="local-small",
            inferred_mode=Mode.AGENTIC,
            confidence_percent=85,
            model_identity=ModelIdentity("sha256:" + "2" * 64),
            execution_profile=ExecutionProfile(config["execution_profile_id"], frozenset()),
        ),
        ImmutableStateStore(state_dir),
    )

    assert mcp_result["mode"] == direct_result.mode.value
    assert mcp_result["routing_reason"] == direct_result.routing_reason
    assert mcp_result["selection"]["policy_id"] == direct_result.selection.policy.policy_id


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_honors_explicit_mode(tmp_path):
    from mighty_mouse_mcp.server import run_run
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "3" * 64)

    result = run_run(
        str(tmp_path),
        task_category="feature",
        inferred_mode="coding",
        confidence_percent=50,
        user_mode="agentic",
    )

    assert result["mode"] == "agentic"
    assert result["routing_reason"] == "explicit user Mode override"


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_selects_hybrid_for_medium_confidence(tmp_path):
    from mighty_mouse_mcp.server import run_run
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "4" * 64)

    handoff = {
        "handoff_id": "handoff-mcp-01",
        "summary": "Hybrid task summary",
        "constraints": ["Keep tests green"],
        "acceptance_checks": ["Unit tests pass"],
        "file_scope": ["src/"],
        "risks": ["None"],
    }

    result = run_run(
        str(tmp_path),
        task_category="feature",
        inferred_mode="coding",
        confidence_percent=70,
        hybrid_handoff=handoff,
    )

    assert result["mode"] == "hybrid"
    assert result["routing_reason"] == "medium-confidence fixed Hybrid"
    assert result["handoff_record_hash"] is not None


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_requires_hybrid_handoff(tmp_path):
    from mighty_mouse_mcp.server import run_run
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "5" * 64)

    with pytest.raises(ValueError, match="durable Hybrid handoff"):
        run_run(
            str(tmp_path),
            task_category="feature",
            inferred_mode="coding",
            confidence_percent=70,
        )


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_rejects_low_confidence_without_override(tmp_path):
    from mighty_mouse_mcp.server import run_run
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "6" * 64)

    with pytest.raises(ValueError, match="explicit user Mode choice is required below 55%"):
        run_run(
            str(tmp_path),
            task_category="feature",
            inferred_mode="coding",
            confidence_percent=50,
        )


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_builds_hybrid_scope_from_pinned_identity(tmp_path):
    from mighty_mouse_mcp.server import run_run
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "7" * 64, model_class="local-large")

    handoff = {
        "handoff_id": "handoff-mcp-02",
        "summary": "Check pinned scope construction",
        "constraints": ["Constraint 1"],
        "acceptance_checks": ["Check 1"],
        "file_scope": ["src/mcp"],
        "risks": ["Risk 1"],
    }

    result = run_run(
        str(tmp_path),
        task_category="refactoring",
        inferred_mode="hybrid",
        confidence_percent=90,
        hybrid_handoff=handoff,
    )
    assert result["mode"] == "hybrid"
    assert result["handoff_record_hash"] is not None


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_rejects_unconfigured_workspace(tmp_path):
    from mighty_mouse_mcp.server import run_run

    with pytest.raises(ValueError, match="not configured"):
        run_run(str(tmp_path))


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_rejects_invalid_adapter_json(tmp_path):
    from mighty_mouse_mcp.server import run_run

    state_dir = tmp_path / ".mighty-mouse"
    state_dir.mkdir()
    (state_dir / "mcp-adapter.json").write_text("{bad json", encoding="utf-8")

    with pytest.raises(ValueError, match="invalid JSON"):
        run_run(str(tmp_path))


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_rejects_stale_tool_contract(tmp_path, monkeypatch):
    import mighty_mouse_mcp.server as server

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "8" * 64)
    monkeypatch.setattr(server, "MCP_TOOL_CONTRACT_VERSION", 99)

    with pytest.raises(ValueError, match="stale"):
        server.run_run(str(tmp_path))


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_v2_workspace_requires_reonboarding_for_v3_contract(tmp_path):
    import mighty_mouse_mcp.server as server

    state_dir = tmp_path / ".mighty-mouse"
    state_dir.mkdir()
    # Build v2 config with contract_version=2
    profile, tool_contract_digest, prompt_template_digest = server.HostAdapter.build_execution_profile(
        runtime_kind="cline",
        runtime_version="3.54.0",
        effective_context_limit=8192,
        tool_signatures=server._get_mcp_tool_signatures(),
        contract_version=2,
    )
    v2_config = {
        "schema_version": 2,
        "repository": "JOHNNYMACONNY/mighty-mouse",
        "model_digest": "sha256:" + "a" * 64,
        "model_class": "local-large",
        "model_source": "host",
        "ollama_model": None,
        "execution_profile_id": profile.profile_id,
        "runtime_kind": "cline",
        "runtime_version": "3.54.0",
        "effective_context_limit": 8192,
        "tool_contract_digest": tool_contract_digest,
        "prompt_template_digest": prompt_template_digest,
    }
    (state_dir / "mcp-adapter.json").write_text(json.dumps(v2_config), encoding="utf-8")

    # With v3 server running, v2 adapter config must fail as stale
    with pytest.raises(ValueError, match="stale"):
        server.run_policy_status(str(tmp_path))
    with pytest.raises(ValueError, match="stale"):
        server.run_run(str(tmp_path))

    # Reonboard with replace=True
    setup_res = server.run_setup_workspace(
        str(tmp_path),
        repository="JOHNNYMACONNY/mighty-mouse",
        model_digest="sha256:" + "a" * 64,
        model_class="local-large",
        runtime_kind="cline",
        runtime_version="3.54.0",
        replace=True,
    )
    assert setup_res["configured"] is True

    # Now run, policy tools, and verify_and_record succeed
    assert server.run_policy_status(str(tmp_path))["scope"]["mode"] == "coding"
    assert server.run_run(str(tmp_path))["mode"] == "coding"
    assert server.run_verify_and_record(
        str(tmp_path), test_command=[sys.executable, "-c", "print('ok')"],
    )["signal_recorded"] is True


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_policy_status_returns_structured_projection(tmp_path):
    from mighty_mouse_mcp.server import run_policy_status
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "b" * 64, model_class="local-small")

    status = run_policy_status(str(tmp_path), mode="coding", task_category="feature")
    assert status["scope"]["mode"] == "coding"
    assert status["scope"]["task_category"] == "feature"
    assert status["scope"]["repository"] == "JOHNNYMACONNY/mighty-mouse"
    assert status["selection"]["policy_id"] == "safe-baseline-coding"
    assert status["signals"]["receipt_count"] == 0
    assert "eligible_successors" in status


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_policy_preview_evaluates_candidate_without_mutating_selection(tmp_path):
    from mighty_mouse_mcp.server import run_policy_preview, run_policy_status
    from mighty_mouse.v2.foundation import (
        Candidate,
        EligibleSuccessor,
        EvidenceBundle,
        ExecutionProfile,
        Experiment,
        ExperimentDecision,
        ExperimentOutcome,
        FreshHoldout,
        ImmutableStateStore,
        Mode,
        ModelIdentity,
        Policy,
        Scope,
        TaskCategory,
    )

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "c" * 64, model_class="local-large")
    adapter_config = json.loads((tmp_path / ".mighty-mouse" / "mcp-adapter.json").read_text())
    profile_id = adapter_config["execution_profile_id"]
    model_digest = "sha256:" + "c" * 64
    store = ImmutableStateStore(tmp_path / ".mighty-mouse")
    scope = Scope(Mode.CODING, "JOHNNYMACONNY/mighty-mouse", TaskCategory.UNKNOWN, "local-large")

    candidate = Candidate(
        candidate_id="candidate-123",
        policy=Policy(policy_id="policy-123", mode=Mode.CODING, version="1"),
        scope=scope,
        model_digest=model_digest,
        required_capabilities=frozenset(),
        compatible_execution_profiles=frozenset({profile_id}),
    )
    store.append_candidate(candidate)
    store.append(EvidenceBundle("evidence-123", "experiment-123", model_digest, profile_id, "sha256:" + "1" * 64))
    store.append(Experiment(
        "experiment-123", "generation-123", "candidate-000", model_digest, profile_id,
        (candidate.candidate_id,), ("evidence-123",), ("sha256:" + "1" * 64,), (),
        (("safety", True), ("security", True), ("provenance", True), ("integrity", True), ("freshness", True)), "v2",
        ExperimentOutcome.COMPLETED, ExperimentDecision.NOMINATE, candidate.candidate_id,
    ))
    store.append(FreshHoldout(
        candidate.candidate_id, scope, model_digest, profile_id, True,
        "experiment-123", "evidence-123", "sha256:manifest", "sha256:corpus",
        "v2", (("holdout-task", "sha256:task"),),
    ))
    store.append_eligible_successor(
        EligibleSuccessor(candidate, "experiment-123", "evidence-123"),
        model_identity=ModelIdentity(model_digest),
        execution_profile=ExecutionProfile(profile_id, frozenset()),
    )

    preview = run_policy_preview(str(tmp_path), candidate_id="candidate-123", evidence_bundle_id="evidence-123")
    assert preview["interface"] == "policy_preview"
    assert preview["preview_id"].startswith("preview-")
    assert preview["selection"]["policy_id"] == "policy-123"
    assert preview["selection"]["source"] == "preview"

    status = run_policy_status(str(tmp_path))
    assert status["selection"]["policy_id"] == "safe-baseline-coding"


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_policy_pin_persists_pin_record(tmp_path):
    from mighty_mouse_mcp.server import run_policy_pin
    from mighty_mouse.v2.foundation import (
        Candidate,
        EligibleSuccessor,
        ImmutableStateStore,
        Mode,
        Policy,
        Promotion,
        Scope,
        TaskCategory,
    )

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "d" * 64, model_class="local-large")
    adapter_config = json.loads((tmp_path / ".mighty-mouse" / "mcp-adapter.json").read_text())
    profile_id = adapter_config["execution_profile_id"]
    model_digest = "sha256:" + "d" * 64
    store = ImmutableStateStore(tmp_path / ".mighty-mouse")
    scope = Scope(Mode.CODING, "JOHNNYMACONNY/mighty-mouse", TaskCategory.UNKNOWN, "local-large")

    candidate = Candidate(
        candidate_id="candidate-456",
        policy=Policy("policy-456", Mode.CODING, "v1.0"),
        scope=scope,
        model_digest=model_digest,
        required_capabilities=frozenset(),
        compatible_execution_profiles=frozenset({profile_id}),
    )
    store.append_promotion(Promotion(
        eligible_successor=EligibleSuccessor(candidate, "exp-456", "bundle-456"),
        prior_champion_id=None,
        machine_gates_passed=True,
    ))

    pin = run_policy_pin(str(tmp_path), candidate_id="candidate-456")
    assert pin["interface"] == "policy_pin"
    assert pin["pin_id"].startswith("pin-")
    assert pin["candidate_id"] == "candidate-456"
    assert len(pin["record_hash"]) == 64


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_policy_rollback_recovers_champion_and_records_notice(tmp_path):
    from mighty_mouse_mcp.server import run_policy_rollback
    from mighty_mouse.v2.foundation import (
        Candidate,
        EligibleSuccessor,
        ImmutableStateStore,
        Mode,
        Policy,
        Promotion,
        Scope,
        TaskCategory,
    )

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "e" * 64, model_class="local-large")

    with pytest.raises(ValueError, match="Recovery requires a current exact compatible Champion"):
        run_policy_rollback(str(tmp_path), reason="user_requested")

    store = ImmutableStateStore(tmp_path / ".mighty-mouse")
    scope = Scope(Mode.CODING, "JOHNNYMACONNY/mighty-mouse", TaskCategory.UNKNOWN, "local-large")
    adapter_config = json.loads((tmp_path / ".mighty-mouse" / "mcp-adapter.json").read_text())
    candidate = Candidate(
        candidate_id="candidate-champion-1",
        policy=Policy("policy-champion-1", Mode.CODING, "v1.0"),
        scope=scope,
        model_digest="sha256:" + "e" * 64,
        required_capabilities=frozenset(),
        compatible_execution_profiles=frozenset({adapter_config["execution_profile_id"]}),
    )
    store.append_promotion(Promotion(
        eligible_successor=EligibleSuccessor(candidate, "exp-1", "bundle-1"),
        prior_champion_id=None,
        machine_gates_passed=True,
    ))

    rollback = run_policy_rollback(
        str(tmp_path),
        reason="verified_security_guard_failure",
        security_breach=True,
    )
    assert rollback["interface"] == "policy_rollback"
    assert rollback["reason"] == "verified_security_guard_failure"
    assert rollback["security_breach"] is True
    assert rollback["action"] == "restricted_and_rolled_back"
    assert rollback["candidate_id"] == "candidate-champion-1"


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_policy_tools_reject_unconfigured_or_stale_workspaces(tmp_path, monkeypatch):
    import mighty_mouse_mcp.server as server

    with pytest.raises(ValueError, match="not configured"):
        server.run_policy_status(str(tmp_path))

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "f" * 64)
    monkeypatch.setattr(server, "MCP_TOOL_CONTRACT_VERSION", 99)

    with pytest.raises(ValueError, match="stale"):
        server.run_policy_status(str(tmp_path))
    with pytest.raises(ValueError, match="stale"):
        server.run_policy_preview(str(tmp_path), candidate_id="candidate-1")
    with pytest.raises(ValueError, match="stale"):
        server.run_policy_pin(str(tmp_path), candidate_id="candidate-1")
    with pytest.raises(ValueError, match="stale"):
        server.run_policy_rollback(str(tmp_path), reason="test")


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_mcp_run_persists_routing_and_handoff_records(tmp_path):
    from mighty_mouse_mcp.server import run_run
    configure_cline_adapter(tmp_path, model_digest="sha256:" + "9" * 64)

    # 1. Non-hybrid run -> persists routing, handoff_record_hash is None
    res1 = run_run(str(tmp_path), confidence_percent=100)
    assert res1["routing_record_hash"] is not None
    assert res1["handoff_record_hash"] is None

    # 2. Hybrid run -> persists both
    handoff = {
        "handoff_id": "handoff-persists-01",
        "summary": "Check record persistence",
        "constraints": ["C1"],
        "acceptance_checks": ["A1"],
        "file_scope": ["src/"],
        "risks": ["R1"],
    }
    res2 = run_run(
        str(tmp_path),
        user_mode="hybrid",
        hybrid_handoff=handoff,
    )
    assert res2["routing_record_hash"] is not None
    assert res2["handoff_record_hash"] is not None


@pytest.mark.skipif(not mcp_stdio_available, reason="MCP stdio client is not installed")
def test_stdio_server_lists_and_calls_tools():
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise_server():
        with (
            tempfile.TemporaryDirectory() as home,
            tempfile.TemporaryDirectory() as workspace,
        ):
            write_ollama_manifest(
                Path(home), GEMMA_MODEL, "sha256:" + "c" * 64
            )
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "mighty_mouse_mcp.server"],
                env={
                    **os.environ,
                    "HOME": home,
                    "PYTHONPATH": os.pathsep.join(
                        filter(
                            None,
                            [
                                os.path.abspath("src"),
                                MCP_SRC,
                                os.environ.get("PYTHONPATH", ""),
                            ],
                        )
                    ),
                },
            )
            async with stdio_client(parameters) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    listed = await session.list_tools()
                    assert {tool.name for tool in listed.tools} == {
                        "protocol",
                        "verify",
                        "verify_and_record",
                        "setup_workspace",
                        "recording_audit",
                        "run",
                        "policy_status",
                        "policy_preview",
                        "policy_pin",
                        "policy_rollback",
                    }
                    response = await session.call_tool(
                        "protocol",
                        {
                            "task_description": "Change one label",
                            "complexity": "low",
                        },
                    )
                    assert not response.isError
                    payload = json.loads(response.content[0].text)
                    assert payload["protocol_version"] == "v9.1"
                    setup = await session.call_tool(
                        "setup_workspace",
                        {
                            "workspace": workspace,
                            "repository": "JOHNNYMACONNY/mighty-mouse",
                            "ollama_model": GEMMA_MODEL,
                            "model_class": "local-small",
                            "effective_context_limit": 8192,
                            "runtime_kind": "cline",
                            "runtime_version": "3.32.2",
                        },
                    )
                    assert not setup.isError
                    run_result = await session.call_tool(
                        "run",
                        {
                            "workspace": workspace,
                            "task_category": "feature",
                            "inferred_mode": "coding",
                            "confidence_percent": 100,
                        },
                    )
                    assert not run_result.isError
                    run_payload = json.loads(run_result.content[0].text)
                    assert run_payload["mode"] == "coding"
                    assert run_payload["routing_reason"] == "high-confidence inferred Mode"
                    recorded = await session.call_tool(
                        "verify_and_record",
                        {
                            "workspace": workspace,
                            "test_command": f'{sys.executable} -c "print(\'ok\')"',
                        },
                    )
                    assert not recorded.isError
                    recorded_payload = json.loads(recorded.content[0].text)
                    assert recorded_payload["signal_recorded"] is True
                    assert list((Path(workspace) / ".mighty-mouse" / "v2-signal-receipts").glob("*.json"))

    anyio.run(exercise_server)
