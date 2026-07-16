import json

import pytest

from store import CompletionStore
from worker import process_job


def test_completed_job_is_skipped(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"completed": ["job-17"]}))
    calls = []

    result = process_job({"id": "job-17"}, CompletionStore(state), calls.append)

    assert result == "skipped"
    assert calls == []
    assert json.loads(state.read_text()) == {"completed": ["job-17"]}


def test_new_job_is_processed_and_recorded(tmp_path):
    state = tmp_path / "state.json"
    calls = []

    result = process_job({"id": "job-18"}, CompletionStore(state), calls.append)

    assert result == "processed"
    assert calls == [{"id": "job-18"}]
    assert json.loads(state.read_text()) == {"completed": ["job-18"]}


def test_handler_failure_is_not_recorded(tmp_path):
    state = tmp_path / "state.json"

    def fail(_job):
        raise RuntimeError("delivery unavailable")

    with pytest.raises(RuntimeError, match="delivery unavailable"):
        process_job({"id": "job-19"}, CompletionStore(state), fail)

    assert not state.exists()


def test_existing_store_entries_are_preserved(tmp_path):
    state = tmp_path / "state.json"
    state.write_text(json.dumps({"completed": ["job-10"]}))

    process_job({"id": "job-20"}, CompletionStore(state), lambda _job: None)

    assert json.loads(state.read_text()) == {"completed": ["job-10", "job-20"]}
