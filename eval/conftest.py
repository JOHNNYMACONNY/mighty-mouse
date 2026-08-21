import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import src.mighty_mouse.orchestrator.mighty_mouse_agent as agent


@pytest.fixture
def agent_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_file = tmp_path / "config.yaml"
    config_file.write_text(
        "provider: sim\n"
        "allow_simulation: true\n"
        "prompt_segments: []\n"
    )
    workspace = tmp_path / "workspace"

    def run(
        task_data,
        responses,
        *,
        stage="unified",
        plan_file=None,
        skills_result=None,
        feedback_str=None,
        temperature=None,
        metadata_sequence=None,
        event_log=None,
        runtime_context=None,
    ):
        task_file = tmp_path / "task.json"
        task_file.write_text(json.dumps(task_data))

        client = MagicMock()
        client.last_metadata = {
            "usage": {"total_tokens": 11},
            "latency_seconds": 0.01,
        }
        if metadata_sequence is None and event_log is None:
            client.generate_content.side_effect = list(responses)
        else:
            response_iter = iter(responses)
            metadata_iter = iter(metadata_sequence or [])

            def generate_content(system_prompt, user_prompt):
                response = next(response_iter)
                if event_log is not None:
                    event_log.append(("provider", response))
                if isinstance(response, BaseException):
                    raise response
                if metadata_sequence is not None:
                    client.last_metadata = next(metadata_iter)
                return response

            client.generate_content.side_effect = generate_content
        client_factory = MagicMock(return_value=client)

        monkeypatch.setattr(agent, "GeminiClient", client_factory)
        monkeypatch.setattr(agent, "_REPO_ROOT", str(tmp_path))
        sleep_calls = []
        monkeypatch.setattr(agent.time, "sleep", sleep_calls.append)
        monkeypatch.setattr(agent.time, "time", lambda: 1700000000)
        if skills_result is not None:
            def fake_load_skills(**_):
                return skills_result

            monkeypatch.setattr(agent, "_load_skills", fake_load_skills)

        solve_kwargs = {
            "workspace": str(workspace),
            "stage": stage,
            "plan_file": str(plan_file) if plan_file else None,
        }
        if feedback_str is not None:
            solve_kwargs["feedback_str"] = feedback_str
        if temperature is not None:
            solve_kwargs["temperature"] = temperature
        if runtime_context is not None:
            solve_kwargs["runtime_context"] = runtime_context

        agent._solve_inner(
            str(config_file),
            str(task_file),
            **solve_kwargs,
        )

        metadata_path = workspace / "logs" / "last_agent_run.json"
        metadata = json.loads(metadata_path.read_text())
        return SimpleNamespace(
            client=client,
            client_factory=client_factory,
            metadata=metadata,
            raw_logs=sorted(
                (tmp_path / "logs" / "raw_responses").glob("*.txt")
            ),
            sleep_calls=sleep_calls,
            task_file=task_file,
            workspace=workspace,
        )

    return SimpleNamespace(
        config_file=config_file,
        workspace=workspace,
        run=run,
        root=tmp_path,
    )
