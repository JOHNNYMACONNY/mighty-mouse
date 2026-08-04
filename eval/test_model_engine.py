"""Tests for ModelExecutionEngine in Mighty Mouse Orchestrator."""

import pytest
from mighty_mouse.orchestrator.model_engine import ModelExecutionEngine


def test_model_execution_engine_sim():
    config = {
        "provider": "sim",
        "allow_simulation": True,
        "model": "sim-model",
    }
    engine = ModelExecutionEngine(config)
    res = engine.generate("Hello world", require_json=False)
    assert "text" in res
    assert "metadata" in res
    assert engine.estimate_tokens("Hello world!") == 3


def test_model_execution_engine_require_json(monkeypatch):
    config = {
        "provider": "sim",
        "allow_simulation": True,
        "model": "sim-model",
    }
    engine = ModelExecutionEngine(config)
    monkeypatch.setattr(engine.client, "generate_content", lambda sys, prompt: '{"key": "value"}')
    res = engine.generate('{"key": "value"}', system_instruction="Respond with JSON", require_json=True)
    assert res["parsed"] == {"key": "value"}


def test_model_execution_engine_token_estimator():
    engine = ModelExecutionEngine({"provider": "sim", "allow_simulation": True})
    assert engine.estimate_tokens("12345678") == 2
