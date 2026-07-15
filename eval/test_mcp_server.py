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

try:
    from mcp.server.fastmcp import FastMCP  # noqa: F401
except ImportError:
    mcp_available = False
else:
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
    write_ollama_manifest(home, "gpt-oss:20b", digest)
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    result = run_setup_workspace(
        str(workspace),
        repository="JOHNNYMACONNY/mighty-mouse",
        ollama_model="gpt-oss:20b",
        model_class="local-large",
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
        ollama_model="gpt-oss:20b",
        model_class="local-large",
        effective_context_limit=8192,
        runtime_kind="cline",
        runtime_version="3.32.2",
    )["configured"] is False

    with pytest.raises(ValueError, match="runtime kind"):
        run_setup_workspace(
            str(workspace), repository="JOHNNYMACONNY/mighty-mouse", ollama_model="gpt-oss:20b",
            model_class="local-large", runtime_kind="unknown", runtime_version="unknown",
        )

    write_ollama_manifest(home, "gpt-oss:20b", "sha256:" + "b" * 64)
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
        "contract_version", "protocol", "verify", "setup_workspace", "verify_and_record", "recording_audit",
    }


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_recording_requires_reonboarding_after_a_tool_contract_change(tmp_path, monkeypatch):
    import mighty_mouse_mcp.server as server

    configure_cline_adapter(tmp_path, model_digest="sha256:" + "7" * 64)
    monkeypatch.setattr(server, "MCP_TOOL_CONTRACT_VERSION", 2)
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
def test_stdio_server_lists_and_calls_tools():
    import anyio
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def exercise_server():
        parameters = StdioServerParameters(
            command=sys.executable,
            args=["-m", "mighty_mouse_mcp.server"],
            env={
                **os.environ,
                "PYTHONPATH": os.pathsep.join(
                    filter(None, [os.path.abspath("src"), MCP_SRC, os.environ.get("PYTHONPATH", "")])
                ),
            },
        )
        async with stdio_client(parameters) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                listed = await session.list_tools()
                assert {tool.name for tool in listed.tools} == {
                    "protocol", "verify", "verify_and_record", "setup_workspace", "recording_audit",
                }
                response = await session.call_tool(
                    "protocol",
                    {"task_description": "Change one label", "complexity": "low"},
                )
                assert not response.isError
                payload = json.loads(response.content[0].text)
                assert payload["protocol_version"] == "v9.1"
                with tempfile.TemporaryDirectory() as workspace:
                    setup = await session.call_tool(
                        "setup_workspace",
                        {
                            "workspace": workspace,
                            "repository": "JOHNNYMACONNY/mighty-mouse",
                            "ollama_model": "gpt-oss:20b",
                            "model_class": "local-large",
                            "effective_context_limit": 8192,
                            "runtime_kind": "cline",
                            "runtime_version": "3.32.2",
                        },
                    )
                    assert not setup.isError
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
