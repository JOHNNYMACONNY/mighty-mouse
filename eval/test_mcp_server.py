import os
import sys
import json
import tempfile
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
    state_dir = workspace / ".mighty-mouse"
    state_dir.mkdir()
    (state_dir / "cline-adapter.json").write_text(json.dumps({
        "repository": "JOHNNYMACONNY/mighty-mouse",
        "model_digest": model_digest,
        "model_class": model_class,
        "execution_profile_id": "sha256:" + "d" * 64,
    }), encoding="utf-8")


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
    config = tmp_path / ".mighty-mouse" / "cline-adapter.json"
    document = json.loads(config.read_text())
    document["execution_profile_id"] = "unknown"
    config.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(ValueError, match="exact execution profile"):
        run_verify_and_record(str(tmp_path))


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
                assert {tool.name for tool in listed.tools} == {"protocol", "verify", "verify_and_record"}
                response = await session.call_tool(
                    "protocol",
                    {"task_description": "Change one label", "complexity": "low"},
                )
                assert not response.isError
                payload = json.loads(response.content[0].text)
                assert payload["protocol_version"] == "v9.1"
                with tempfile.TemporaryDirectory() as workspace:
                    configure_cline_adapter(Path(workspace), model_digest="sha256:" + "c" * 64)
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
