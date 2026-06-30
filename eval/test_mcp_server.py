import os
import sys
import json

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


@pytest.mark.skipif(not mcp_available, reason="MCP optional dependency is not installed")
def test_protocol_depth_scales():
    from mighty_mouse_mcp.server import run_protocol

    low = run_protocol("Change one label", "low")
    high = run_protocol("Refactor persistence", "high")

    assert low["protocol_version"] == "v9.1"
    assert "<scope>" in low["protocol_prompt"]
    assert "12. Search semantic synonyms" in high["protocol_prompt"]
    assert len(high["protocol_prompt"]) > len(low["protocol_prompt"])


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
                assert {tool.name for tool in listed.tools} == {"protocol", "verify"}
                response = await session.call_tool(
                    "protocol",
                    {"task_description": "Change one label", "complexity": "low"},
                )
                assert not response.isError
                payload = json.loads(response.content[0].text)
                assert payload["protocol_version"] == "v9.1"

    anyio.run(exercise_server)
