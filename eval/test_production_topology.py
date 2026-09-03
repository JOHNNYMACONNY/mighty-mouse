"""Regression and contract tests for production topology rollout.

Enforces Ticket 08 decision: MM_SINGLE_ALWAYS
- Default/recommended production coding topology is canonical single-agent
  execution through HostAdapter.solve / agent_execute.
- Swarm execution (HostAdapter.solve_swarm / swarm_execute) remains available
  as an explicit opt-in compatibility interface only.
- No implicit or default production path routes to swarm.
- MCP remains contract version 6 with exactly 15 tools.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from mighty_mouse.host.adapter import HostAdapter
from mighty_mouse.host.recovery_execution import (
    RecoveryExecutionAttempt,
)
from mighty_mouse.orchestrator.mighty_mouse_agent import _build_cli_parser
import mighty_mouse_mcp.server as server


def test_cli_default_mode_is_single():
    """Verify production CLI parser defaults to single mode."""
    parser = _build_cli_parser()
    args = parser.parse_args(["dummy_cfg.yaml", "dummy_task.json"])
    assert args.mode == "single", (
        "Production CLI default mode must be 'single'"
    )
    assert args.concurrency == 1

    swarm_args = parser.parse_args(
        ["dummy_cfg.yaml", "dummy_task.json", "--mode", "swarm"]
    )
    assert swarm_args.mode == "swarm"
    assert swarm_args.concurrency == 1


def test_agent_execute_dispatches_to_host_adapter_solve(tmp_path: Path):
    """Verify agent_execute calls HostAdapter.solve and never solve_swarm."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    logs_dir = ws / "logs"
    logs_dir.mkdir()
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model: gemma4:e4b\n", encoding="utf-8")
    task = tmp_path / "task.json"
    task.write_text('{"id": "t1"}', encoding="utf-8")

    mock_metadata = {
        "task_id": "t1",
        "pass_type": "clean",
        "output_files": ["foo.py"],
        "written_files": ["foo.py"],
        "deleted_files": [],
        "schema_error": False,
        "attempts": 1,
    }
    (logs_dir / "last_agent_run.json").write_text(
        json.dumps(mock_metadata), encoding="utf-8"
    )

    with patch.object(HostAdapter, "solve") as mock_solve, patch.object(
        HostAdapter, "solve_swarm"
    ) as mock_solve_swarm:
        result = server.run_agent_execute(
            workspace=str(ws),
            p_cfg_path=str(cfg),
            task_input=str(task),
        )
        assert mock_solve.called, "agent_execute must call HostAdapter.solve"
        assert not mock_solve_swarm.called, (
            "agent_execute must never call HostAdapter.solve_swarm"
        )
        assert result["interface"] == "agent_execute"
        assert result["task_id"] == "t1"


def test_swarm_execute_calls_host_adapter_solve_swarm_only_explicitly(
    tmp_path: Path,
):
    """Verify swarm_execute explicitly dispatches to solve_swarm."""
    ws = tmp_path / "workspace"
    ws.mkdir()
    v_ws = tmp_path / "verification_workspace"
    v_ws.mkdir()
    task = {"id": "t2", "title": "Test swarm"}

    mock_solve_result = {
        "pipeline_result": {
            "turn": 1,
            "review": {"verdict": "PASS", "reason": "Looks good"},
            "verification": {"passed": True, "summary": "1/1 passed"},
            "application": {"applied_output_paths": ["bar.py"]},
            "elapsed_sec": 1.2,
        },
        "host_provenance": {
            "repository": "test-repo",
            "model_class": "local-small",
            "model_digest": "sha256:abcd",
            "execution_profile_id": "profile-1",
            "model_source": "ollama",
            "ollama_model": "gemma4:e4b",
            "contract_version": 6,
        },
    }

    with patch.object(
        HostAdapter, "solve_swarm", return_value=mock_solve_result
    ) as mock_solve_swarm, patch.object(
        HostAdapter, "solve"
    ) as mock_solve:
        result = server.run_swarm_execute(
            workspace=str(ws),
            verification_workspace=str(v_ws),
            task=task,
        )
        assert mock_solve_swarm.called, (
            "swarm_execute must call HostAdapter.solve_swarm"
        )
        assert not mock_solve.called, (
            "swarm_execute must not call HostAdapter.solve"
        )
        assert result["interface"] == "swarm_execute"
        assert result["review"]["verdict"] == "PASS"


def test_mcp_run_is_selector_only_and_does_not_execute(tmp_path: Path):
    """Verify MCP run tool is selector-only and never invokes execution."""
    ws = tmp_path / "workspace"
    ws.mkdir()

    with patch(
        "mighty_mouse_mcp.server.run_autopilot"
    ) as mock_autopilot, patch.object(
        HostAdapter, "resolve_adapter_context"
    ) as mock_resolve, patch.object(
        HostAdapter, "solve"
    ) as mock_solve, patch.object(
        HostAdapter, "solve_swarm"
    ) as mock_solve_swarm:
        mock_ctx = MagicMock()
        mock_ctx.repository = "test-repo"
        mock_ctx.state_dir = str(tmp_path / ".mighty-mouse")
        mock_ctx.model_class = "local-small"
        mock_ctx.model_identity = MagicMock()
        mock_ctx.execution_profile = MagicMock()
        mock_resolve.return_value = mock_ctx

        mock_autopilot_result = MagicMock()
        mock_autopilot_result.mode.value = "coding"
        mock_autopilot_result.routing_reason = "confidence"
        mock_autopilot_result.selection.policy.policy_id = "pol-1"
        mock_autopilot_result.selection.policy.version = 1
        mock_autopilot_result.selection.source = "store"
        mock_autopilot_result.selection.reason = "pinned"
        mock_autopilot_result.selection.record_hash = "h1"
        mock_autopilot_result.handoff_record_hash = None
        mock_autopilot_result.routing_record_hash = "rh1"
        mock_autopilot.return_value = mock_autopilot_result

        result = server.run_run(workspace=str(ws))
        assert result["interface"] == "run"
        assert result["mode"] == "coding"
        assert not mock_solve.called, "run must not invoke HostAdapter.solve"
        assert not mock_solve_swarm.called, (
            "run must not invoke HostAdapter.solve_swarm"
        )


def test_mcp_tool_contract_version_and_tool_count():
    """Ensure MCP contract version remains 6 with exactly 15 tools."""
    assert server.MCP_TOOL_CONTRACT_VERSION == 6
    signatures = server._get_mcp_tool_signatures()
    assert len(signatures) == 15
    assert "agent_execute" in signatures
    assert "swarm_execute" in signatures
    assert "run" in signatures


def test_host_hook_recovery_execution_mode_is_single_agent_only():
    """Verify that host recovery mode strictly permits only single-agent."""
    attempt = RecoveryExecutionAttempt(
        attempted=True,
        completed=True,
        attempts=1,
        execution_mode="agent",
        output_paths=("foo.py",),
    )
    assert attempt.execution_mode == "agent"

    with pytest.raises(ValueError, match="execution_mode must be 'agent'"):
        RecoveryExecutionAttempt(
            attempted=True,
            completed=True,
            attempts=1,
            execution_mode="swarm",  # type: ignore[arg-type]
            output_paths=("foo.py",),
        )


def test_normal_solve_and_host_adapter_solve_return_none(tmp_path: Path):
    """Verify solve and HostAdapter.solve preserve the -> None contract."""
    from mighty_mouse.orchestrator.mighty_mouse_agent import (
        solve,
        _solve_with_runtime_context,
    )
    from mighty_mouse.host.adapter import (
        HostAdapter,
        AdapterRuntimeContext,
        ExecutionProfile,
        ModelIdentity,
    )

    cfg = tmp_path / "cfg.yaml"
    cfg.write_text(
        "model: test\nprovider: sim\nallow_simulation: true\n",
        encoding="utf-8",
    )
    task = tmp_path / "task.json"
    task.write_text(
        json.dumps({"id": "t1", "expected_files": ["a.py"]}),
        encoding="utf-8",
    )

    with patch(
        "mighty_mouse.orchestrator.gemini_client."
        "GeminiClient.generate_content",
        return_value="```python:a.py\ncode\n```",
    ):
        # 1. Normal solve() must return None
        res_solve = solve(str(cfg), str(task), workspace=str(tmp_path))
        assert res_solve is None, (
            f"solve() must return None, got {res_solve}"
        )

        # 2. HostAdapter.solve() must return None
        adapter = HostAdapter()
        dummy_profile = ExecutionProfile(
            profile_id="prof-1",
            runtime_kind="antigravity",
            runtime_version="1.0.0",
            effective_context_limit=32000,
            tool_contract_digest="sha256:abc",
            prompt_template_digest="sha256:def",
            sampling_settings={},
            resource_limits={},
            capabilities=frozenset({"mcp"}),
        )
        dummy_ctx = AdapterRuntimeContext(
            state_dir=tmp_path / ".mighty-mouse",
            repository="test/repo",
            model_class="gemma-27b",
            model_identity=ModelIdentity(artifact_digest="sha256:111"),
            execution_profile=dummy_profile,
            model_source="host",
        )
        with patch.object(
            adapter, "resolve_adapter_context", return_value=dummy_ctx
        ):
            res_adapter = adapter.solve(
                str(tmp_path),
                str(cfg),
                str(task),
                tool_signatures=("run",),
            )
            assert res_adapter is None, (
                f"HostAdapter.solve() must return None, got {res_adapter}"
            )

        # 3. Recovery mode must return output paths
        res_recovery = _solve_with_runtime_context(
            str(cfg),
            str(task),
            workspace=str(tmp_path),
            allowed_write_paths=("a.py",),
            recovery_mode=True,
        )
        assert res_recovery == ["a.py"]
