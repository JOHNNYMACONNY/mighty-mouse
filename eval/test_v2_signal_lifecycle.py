from datetime import datetime, timedelta, timezone
import json
import sys

import pytest

from mighty_mouse import cli
from mighty_mouse.v2.foundation import Mode, Scope, Signal, TaskCategory
from mighty_mouse.v2.signals import SignalLifecycle


def _signal(**changes):
    values = {
        "signal_id": "signal-001",
        "scope": Scope(Mode.CODING, "JOHNNYMACONNY/mighty-mouse", TaskCategory.FEATURE, "local-small"),
        "model_digest": "sha256:" + "a" * 64,
        "execution_profile_id": "codex-local",
        "outcome": "passed",
        "duration_ms": 120,
        "retry_count": 1,
        "verifier_category": "tests",
        "verifier_result": "passed",
        "environment_metadata": (("os", "macos"), ("runtime", "codex")),
        "rating": 5,
    }
    values.update(changes)
    return Signal(**values)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("outcome", "passed; prompt=do this"),
        ("verifier_category", "src/mighty_mouse"),
        ("environment_metadata", (("path", "/Users/example/project"),)),
        ("model_digest", "sha256:sk-live-secret"),
    ],
)
def test_signal_schema_rejects_content_bearing_values(field, value):
    with pytest.raises(ValueError, match="controlled|content-free|sha256 digest"):
        _signal(**{field: value})


@pytest.mark.parametrize(
    ("field", "value"),
    [("duration_ms", float("nan")), ("duration_ms", float("inf")), ("retry_count", True), ("rating", True)],
)
def test_signal_schema_rejects_malformed_numeric_values(field, value):
    with pytest.raises(ValueError, match="integer"):
        _signal(**{field: value})


def test_collection_pause_blocks_new_receipts_and_resumes(tmp_path):
    lifecycle = SignalLifecycle(tmp_path)

    lifecycle.pause()
    assert lifecycle.collect(_signal()) is None
    assert lifecycle.history()["receipt_count"] == 0

    lifecycle.resume()
    stored = lifecycle.collect(_signal())

    assert stored is not None
    assert lifecycle.history()["receipt_count"] == 1


def test_history_only_exposes_safe_aggregates(tmp_path):
    lifecycle = SignalLifecycle(tmp_path)
    lifecycle.collect(_signal(signal_id="signal-001"))
    lifecycle.collect(_signal(signal_id="signal-002", outcome="failed", verifier_result="failed"))

    history = lifecycle.history()

    assert history["receipt_count"] == 2
    assert history["aggregates"][0]["count"] == 1
    assert "signal_id" not in str(history)
    assert "exact-model" not in str(history)
    assert set(history) == {"collection_paused", "receipt_count", "aggregates"}


def test_compaction_moves_expired_receipts_to_durable_aggregates(tmp_path):
    lifecycle = SignalLifecycle(tmp_path)
    collected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lifecycle.collect(_signal(), now=collected_at)

    compacted = lifecycle.compact(now=collected_at + timedelta(days=30))
    history = lifecycle.history(now=collected_at + timedelta(days=30))

    assert compacted == 1
    assert history["receipt_count"] == 0
    assert history["aggregates"] == [{
        "repository": "JOHNNYMACONNY/mighty-mouse", "mode": "coding", "task_category": "feature", "model_class": "local-small",
        "outcome": "passed", "verifier_category": "tests", "verifier_result": "passed",
        "rating": 5, "count": 1, "total_duration_ms": 120, "total_retry_count": 1,
    }]


def test_compaction_preserves_the_append_only_chain_for_retained_receipts(tmp_path):
    lifecycle = SignalLifecycle(tmp_path)
    collected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    lifecycle.collect(_signal(signal_id="signal-001"), now=collected_at)
    lifecycle.collect(_signal(signal_id="signal-002"), now=collected_at + timedelta(days=1))

    receipt_path = next(lifecycle.receipt_dir.glob("*.json"))
    receipt_bytes = receipt_path.read_bytes()
    lifecycle.compact(now=collected_at + timedelta(days=30))

    assert lifecycle.history(now=collected_at + timedelta(days=30))["receipt_count"] == 1
    assert receipt_path.read_bytes() == receipt_bytes


def test_aggregate_history_and_purge_remain_scoped_to_one_repository(tmp_path):
    lifecycle = SignalLifecycle(tmp_path)
    collected_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = _signal(scope=Scope(Mode.CODING, "owner/one", TaskCategory.FEATURE, "local-small"))
    second = _signal(signal_id="signal-002", scope=Scope(Mode.CODING, "owner/two", TaskCategory.FEATURE, "local-small"))
    lifecycle.collect(first, now=collected_at)
    lifecycle.collect(second, now=collected_at)
    lifecycle.compact(now=collected_at + timedelta(days=30))

    assert lifecycle.history(scope=first.scope, now=collected_at + timedelta(days=30))["aggregates"][0]["count"] == 1
    assert lifecycle.purge(scope=first.scope) == 1
    assert lifecycle.history(scope=second.scope, now=collected_at + timedelta(days=30))["aggregates"][0]["count"] == 1


def test_purge_does_not_resume_a_paused_collection(tmp_path):
    lifecycle = SignalLifecycle(tmp_path)
    lifecycle.pause()
    lifecycle.purge()

    assert lifecycle.collection_paused is True


def test_purge_removes_signal_stores_without_touching_immutable_state(tmp_path):
    lifecycle = SignalLifecycle(tmp_path)
    lifecycle.collect(_signal())
    immutable_state = tmp_path / "v2-state.jsonl"
    immutable_state.write_text('{"unrelated":"immutable"}\n', encoding="utf-8")
    before = immutable_state.read_bytes()

    removed = lifecycle.purge()

    assert removed == 1
    assert lifecycle.history()["receipt_count"] == 0
    assert lifecycle.history()["aggregates"] == []
    assert immutable_state.read_bytes() == before


def test_signal_cli_collects_and_renders_only_aggregate_history(monkeypatch, tmp_path, capsys):
    collect_argv = [
        "mighty-mouse", "signals", "collect", "--state-dir", str(tmp_path),
        "--signal-id", "signal-001", "--repository", "JOHNNYMACONNY/mighty-mouse",
        "--mode", "coding", "--task-category", "feature", "--model-class", "local-small",
        "--model-digest", "sha256:" + "a" * 64, "--execution-profile", "codex-local",
        "--outcome", "passed", "--duration-ms", "10", "--retry-count", "0",
        "--verifier-category", "tests", "--verifier-result", "passed", "--json",
    ]
    monkeypatch.setattr(sys, "argv", collect_argv)
    cli.main()
    assert json.loads(capsys.readouterr().out)["collected"] is True

    monkeypatch.setattr(sys, "argv", ["mighty-mouse", "signals", "history", "--state-dir", str(tmp_path), "--json"])
    cli.main()
    history = json.loads(capsys.readouterr().out)

    assert history["interface"] == "signals"
    assert history["history"]["aggregates"][0]["count"] == 1
    assert "signal-001" not in str(history)
