"""Tests for HostAdapter.solve_swarm canonical host provenance binding."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from mighty_mouse.host.adapter import (
    AdapterRuntimeContext,
    HostAdapter,
    MCP_TOOL_CONTRACT_VERSION,
)
from mighty_mouse.v2.foundation import ExecutionProfile, ModelIdentity


TOOL_SIGNATURES: dict[str, Any] = {
    "tool_one": lambda x: x,
    "tool_two": lambda y: y,
}

CLIENT_CLS = (
    "mighty_mouse.orchestrator.ollama_client.OllamaClient.generate_content"
)


def setup_test_manifest(
    home: Path,
    model: str = "gemma4:e4b",
    digest: str = "sha256:" + "a" * 64,
) -> None:
    name, tag = model.rsplit(":", 1)
    manifest_file = (
        home
        / ".ollama"
        / "models"
        / "manifests"
        / "registry.ollama.ai"
        / "library"
        / name
        / tag
    )
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(
        json.dumps(
            {
                "layers": [
                    {
                        "mediaType": (
                            "application/vnd.ollama.image.model"
                        ),
                        "digest": digest,
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def configure_adapter(
    workspace: Path,
    *,
    model_digest: str = "sha256:" + "a" * 64,
    model_class: str = "local-large",
    ollama_model: str | None = "gemma4:e4b",
    model_source: str | None = None,
) -> None:
    state_dir = workspace / ".mighty-mouse"
    state_dir.mkdir(parents=True, exist_ok=True)
    config = HostAdapter.build_adapter_config(
        repository="JOHNNYMACONNY/mighty-mouse",
        model_digest=model_digest,
        model_class=model_class,
        effective_context_limit=8192,
        runtime_kind="cline",
        runtime_version="3.54.0",
        ollama_model=ollama_model,
        tool_signatures=TOOL_SIGNATURES,
        contract_version=MCP_TOOL_CONTRACT_VERSION,
    )
    if model_source is not None:
        config["model_source"] = model_source
    (state_dir / "mcp-adapter.json").write_text(
        json.dumps(config), encoding="utf-8"
    )


def test_adapter_runtime_context_backwards_compatible_construction(tmp_path):
    profile = ExecutionProfile(
        profile_id="prof-1",
        runtime_kind="cline",
        runtime_version="3.54.0",
        effective_context_limit=8192,
        tool_contract_digest="sha256:1",
        prompt_template_digest="sha256:2",
        sampling_settings={},
        resource_limits={},
        capabilities=frozenset(),
    )
    model_id = ModelIdentity(artifact_digest="sha256:abc")
    ctx = AdapterRuntimeContext(
        state_dir=tmp_path,
        repository="repo",
        model_class="local",
        model_identity=model_id,
        execution_profile=profile,
    )
    assert ctx.model_source == "host"
    assert ctx.ollama_model is None


def test_solve_swarm_exact_configured_ollama_model(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    model_name = "qwen2.5-coder:7b"
    model_digest = "sha256:" + "b" * 64
    setup_test_manifest(
        tmp_path / "home", model=model_name, digest=model_digest
    )

    real_ws = tmp_path / "real_ws"
    real_ws.mkdir()
    (real_ws / "code.py").write_text("initial = 1\n")

    iso_ws = tmp_path / "iso_ws"
    iso_ws.mkdir()
    (iso_ws / "code.py").write_text("initial = 1\n")

    configure_adapter(
        real_ws,
        model_digest=model_digest,
        model_class="local-small",
        ollama_model=model_name,
    )

    task_input = json.dumps(
        {
            "id": "T1",
            "instruction": "Update code",
            "files": ["code.py"],
        }
    )

    adapter = HostAdapter()

    plan_resp = """<swarm_plan>
## 1. Task Understanding
Update code.
## 2. Mandatory Dependency Audit
- code.py (MODIFY)
## 3. Authorized File Impact Map
- code.py (MODIFY)
## 4. Implementation Steps
1. Update code.py
</swarm_plan>"""

    code_resp = """<act>
[FILE: code.py]
```python
initial = 2
```
</act>"""

    recorded_models = []

    def mock_generate(self, sys_instr, user_prompt):
        recorded_models.append(self.model_name)
        if "PLANNER" in sys_instr or "blueprint" in sys_instr.lower():
            return plan_resp
        if "CODER" in sys_instr or "code" in sys_instr.lower():
            return code_resp
        return ""

    with patch(CLIENT_CLS, mock_generate):
        result = adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
            test_command=[sys.executable, "-c", "print('tests pass')"],
        )

    # Prove Swarm used the exact configured model
    assert len(recorded_models) >= 2
    for used_model in recorded_models:
        assert used_model == model_name

    # Prove return structure is JSON-safe and contains host provenance
    assert result["host_provenance"]["model_source"] == "ollama"
    assert result["host_provenance"]["ollama_model"] == model_name
    assert result["host_provenance"]["model_digest"] == model_digest
    assert (
        result["host_provenance"]["repository"]
        == "JOHNNYMACONNY/mighty-mouse"
    )
    assert result["host_provenance"]["contract_version"] == 5

    # Prove real application occurred exactly once on verification PASS
    assert (real_ws / "code.py").read_text() == "initial = 2"
    assert result["pipeline_result"]["application"]["occurred"] is True
    assert (
        result["pipeline_result"]["application"]["applied_output_paths"]
        == ["code.py"]
    )
    # Prove isolated template workspace was untouched
    assert (iso_ws / "code.py").read_text() == "initial = 1\n"
    # Result is JSON serializable
    assert json.loads(json.dumps(result)) == result


def test_solve_swarm_rejects_host_model_source(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    real_ws = tmp_path / "real_ws"
    real_ws.mkdir()
    iso_ws = tmp_path / "iso_ws"
    iso_ws.mkdir()

    configure_adapter(
        real_ws,
        model_digest="sha256:" + "a" * 64,
        ollama_model=None,
    )

    adapter = HostAdapter()
    task_input = json.dumps({"id": "T1"})

    with pytest.raises(
        ValueError, match="requires an Ollama-backed model identity"
    ):
        adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
        )


def test_solve_swarm_rejects_stale_or_missing_adapter(tmp_path):
    real_ws = tmp_path / "real_ws"
    real_ws.mkdir()
    iso_ws = tmp_path / "iso_ws"
    iso_ws.mkdir()

    adapter = HostAdapter()
    task_input = json.dumps({"id": "T1"})

    with pytest.raises(ValueError, match="identity is not configured"):
        adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
        )


def test_solve_swarm_rejects_invalid_task_input(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    setup_test_manifest(tmp_path / "home")
    real_ws = tmp_path / "real_ws"
    real_ws.mkdir()
    iso_ws = tmp_path / "iso_ws"
    iso_ws.mkdir()
    configure_adapter(real_ws)

    adapter = HostAdapter()

    with pytest.raises(ValueError, match="invalid JSON"):
        adapter.solve_swarm(
            workspace=str(real_ws),
            task_input="not-json",
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
        )

    with pytest.raises(ValueError, match="valid JSON object"):
        adapter.solve_swarm(
            workspace=str(real_ws),
            task_input="[1, 2, 3]",
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
        )


def test_solve_swarm_rejects_missing_workspaces(monkeypatch, tmp_path):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    setup_test_manifest(tmp_path / "home")
    real_ws = tmp_path / "real_ws"
    iso_ws = tmp_path / "iso_ws"

    adapter = HostAdapter()
    task_input = json.dumps({"id": "T1"})

    with pytest.raises(ValueError, match="Workspace must be an existing"):
        adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
        )

    real_ws.mkdir()
    configure_adapter(real_ws)

    with pytest.raises(
        ValueError, match="Verification workspace must be an existing"
    ):
        adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
        )


def test_solve_swarm_verification_fail_yields_zero_real_applications(
    monkeypatch, tmp_path
):
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    setup_test_manifest(tmp_path / "home")
    real_ws = tmp_path / "real_ws"
    real_ws.mkdir()
    (real_ws / "target.py").write_text("original\n")

    iso_ws = tmp_path / "iso_ws"
    iso_ws.mkdir()
    (iso_ws / "target.py").write_text("original\n")

    configure_adapter(real_ws)
    adapter = HostAdapter()

    task_input = json.dumps(
        {
            "id": "T1",
            "instruction": "Modify target",
            "files": ["target.py"],
        }
    )

    plan_resp = """<swarm_plan>
## 1. Task Understanding
Modify target.
## 2. Mandatory Dependency Audit
- target.py (MODIFY)
## 3. Authorized File Impact Map
- target.py (MODIFY)
## 4. Implementation Steps
1. Corrupt target.py
</swarm_plan>"""

    code_resp = """<act>
[FILE: target.py]
```python
corrupted
```
</act>"""

    def mock_generate(self, sys_instr, user_prompt):
        if "PLANNER" in sys_instr or "blueprint" in sys_instr.lower():
            return plan_resp
        if "CODER" in sys_instr or "code" in sys_instr.lower():
            return code_resp
        return ""

    with patch(CLIENT_CLS, mock_generate):
        result = adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
            test_command=[
                sys.executable,
                "-c",
                "import sys; sys.exit(1)",
            ],
        )

    # Real workspace must remain completely untouched
    assert (real_ws / "target.py").read_text() == "original\n"
    assert result["pipeline_result"]["review"]["verdict"] == "REJECT"
    assert result["pipeline_result"]["application"]["occurred"] is False
    assert (
        result["pipeline_result"]["application"]["applied_output_paths"] == []
    )


def test_solve_swarm_retry_isolation(monkeypatch, tmp_path):
    """Test that turn 1 failure does not contaminate turn 2 disposable copy."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    setup_test_manifest(tmp_path / "home")
    real_ws = tmp_path / "real_ws"
    real_ws.mkdir()
    (real_ws / "app.py").write_text("v0\n")

    iso_ws = tmp_path / "iso_ws"
    iso_ws.mkdir()
    (iso_ws / "app.py").write_text("v0\n")

    configure_adapter(real_ws)
    adapter = HostAdapter()

    task_input = json.dumps(
        {
            "id": "T1",
            "instruction": "Fix app",
            "files": ["app.py"],
        }
    )

    plan_resp = """<swarm_plan>
## 1. Task Understanding
Fix app.
## 2. Mandatory Dependency Audit
- app.py (MODIFY)
## 3. Authorized File Impact Map
- app.py (MODIFY)
## 4. Implementation Steps
1. Fix app.py
</swarm_plan>"""

    coder_turn1 = "[FILE: app.py]\n```python\nv1_broken\n```"
    coder_turn2 = "[FILE: app.py]\n```python\nv2_fixed\n```"

    turn_counter = {"coder": 0}

    def mock_generate(self, sys_instr, user_prompt):
        if "PLANNER" in sys_instr or "blueprint" in sys_instr.lower():
            return plan_resp
        if "CODER" in sys_instr or "code" in sys_instr.lower():
            turn_counter["coder"] += 1
            if turn_counter["coder"] == 1:
                return coder_turn1
            return coder_turn2
        return ""

    test_cmd_str = (
        "import sys, pathlib; text = pathlib.Path('app.py').read_text(); "
        "sys.exit(0 if 'v2_fixed' in text else 1)"
    )
    test_cmd = [sys.executable, "-c", test_cmd_str]

    with patch(CLIENT_CLS, mock_generate):
        result = adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
            test_command=test_cmd,
        )

    # Real workspace has only final v2_fixed applied
    assert (real_ws / "app.py").read_text() == "v2_fixed"
    # Isolated baseline is pristine
    assert (iso_ws / "app.py").read_text() == "v0\n"
    assert result["pipeline_result"]["turn"] == 2
    assert result["pipeline_result"]["application"]["occurred"] is True


def test_solve_swarm_dual_slot_loser_isolation(monkeypatch, tmp_path):
    """Test concurrency=2 where winner is applied and loser is never."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    setup_test_manifest(tmp_path / "home")
    real_ws = tmp_path / "real_ws"
    real_ws.mkdir()
    (real_ws / "out.py").write_text("v0\n")

    iso_ws = tmp_path / "iso_ws"
    iso_ws.mkdir()
    (iso_ws / "out.py").write_text("v0\n")

    configure_adapter(real_ws)
    adapter = HostAdapter()

    task_input = json.dumps(
        {
            "id": "T1",
            "instruction": "Fix out",
            "files": ["out.py"],
        }
    )

    plan_resp = """<swarm_plan>
## 1. Task Understanding
Fix out.
## 2. Mandatory Dependency Audit
- out.py (MODIFY)
## 3. Authorized File Impact Map
- out.py (MODIFY)
## 4. Implementation Steps
1. Fix out.py
</swarm_plan>"""

    coder_slot1 = "[FILE: out.py]\n```python\nwinner\n```"
    coder_slot2 = "[FILE: out.py]\n```python\nloser\n```"

    coder_calls = {"count": 0}

    def mock_generate(self, sys_instr, user_prompt):
        if "PLANNER" in sys_instr or "blueprint" in sys_instr.lower():
            return plan_resp
        if "CODER" in sys_instr or "code" in sys_instr.lower():
            coder_calls["count"] += 1
            if coder_calls["count"] == 1:
                return coder_slot1
            return coder_slot2
        return ""

    with patch(CLIENT_CLS, mock_generate):
        adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
            concurrency=2,
            test_command=[sys.executable, "-c", "print('ok')"],
        )

    # Winner was applied to real workspace
    assert (real_ws / "out.py").read_text() == "winner"
    # Loser was not applied
    assert "loser" not in (real_ws / "out.py").read_text()
    assert (iso_ws / "out.py").read_text() == "v0\n"


def test_solve_swarm_mcp_surface_untouched():
    """Verify MCP tools and contracts remain unchanged by solve_swarm."""
    try:
        from mighty_mouse_mcp.server import _get_mcp_tool_signatures
    except ImportError:
        pytest.skip("mighty_mouse_mcp not available in this test env")

    sigs = _get_mcp_tool_signatures()
    assert len(sigs) == 14
    assert "solve_swarm" not in sigs
    assert "agent_execute" in sigs


def test_solve_swarm_changed_digest_fails_authoritatively(
    monkeypatch, tmp_path
):
    """Prove digest mismatch on disk fails closed before any model call."""
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    real_ws = tmp_path / "real_ws"
    real_ws.mkdir()
    iso_ws = tmp_path / "iso_ws"
    iso_ws.mkdir()

    setup_test_manifest(
        tmp_path / "home", model="gemma4:e4b", digest="sha256:" + "1" * 64
    )
    configure_adapter(
        real_ws,
        model_digest="sha256:" + "1" * 64,
        ollama_model="gemma4:e4b",
    )

    # Now change manifest on disk to simulate layer update
    setup_test_manifest(
        tmp_path / "home", model="gemma4:e4b", digest="sha256:" + "2" * 64
    )

    adapter = HostAdapter()
    task_input = json.dumps({"id": "T1"})

    with pytest.raises(
        ValueError, match="MCP adapter model identity changed"
    ):
        adapter.solve_swarm(
            workspace=str(real_ws),
            task_input=task_input,
            verification_workspace=str(iso_ws),
            tool_signatures=TOOL_SIGNATURES,
        )


def test_direct_swarm_orchestrator_unchanged():
    """Prove direct legacy SwarmOrchestrator constructor and pipeline work."""
    from mighty_mouse.orchestrator.swarm import SwarmOrchestrator

    mock_client = MagicMock()
    orch = SwarmOrchestrator(
        model_name="test-model",
        concurrency=1,
        ollama_client=mock_client,
    )
    assert orch.model_name == "test-model"
    assert orch.concurrency == 1
    assert orch.ollama_client is mock_client
