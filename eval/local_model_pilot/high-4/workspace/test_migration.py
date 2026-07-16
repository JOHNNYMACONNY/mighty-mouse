from unittest.mock import Mock, call
import pytest
from migration import Migration, MigrationStep


def test_migration_all_success():
    state = {"val": 0}

    step1_forward = lambda s: s.update({"val": s["val"] + 1})
    step1_rollback = lambda s: s.update({"val": s["val"] - 1})
    step2_forward = lambda s: s.update({"val": s["val"] * 2})
    step2_rollback = lambda s: s.update({"val": s["val"] // 2})

    step1 = MigrationStep("step1", step1_forward, step1_rollback)
    step2 = MigrationStep("step2", step2_forward, step2_rollback)

    m = Migration([step1, step2])
    m.apply(state)
    assert state["val"] == 2
    assert len(m.applied_steps) == 2


def test_migration_failure_rollback():
    state = {"val": 0, "history": []}

    s1_forward = lambda s: (s.update({"val": 1}), s["history"].append("s1_fw"))
    s1_rollback = lambda s: (s.update({"val": 0}), s["history"].append("s1_rb"))

    def s2_forward(s):
        s["history"].append("s2_fw")
        raise ValueError("s2_failed")

    s2_rollback = lambda s: s["history"].append("s2_rb")

    step1 = MigrationStep("step1", s1_forward, s1_rollback)
    step2 = MigrationStep("step2", s2_forward, s2_rollback)

    m = Migration([step1, step2])

    with pytest.raises(ValueError, match="s2_failed"):
        m.apply(state)

    assert state["val"] == 0
    assert state["history"] == ["s1_fw", "s2_fw", "s1_rb"]


def test_migration_rollback_failure():
    state = {"history": []}

    s1_forward = lambda s: s["history"].append("s1_fw")

    def s1_rollback(s):
        s["history"].append("s1_rb")
        raise KeyError("s1_rb_failed")

    def s2_forward(s):
        s["history"].append("s2_fw")
        raise ValueError("s2_failed")

    s2_rollback = lambda s: s["history"].append("s2_rb")

    step1 = MigrationStep("step1", s1_forward, s1_rollback)
    step2 = MigrationStep("step2", s2_forward, s2_rollback)

    m = Migration([step1, step2])

    with pytest.raises(RuntimeError) as excinfo:
        m.apply(state)

    assert "s2_failed" in str(excinfo.value)
    assert "s1_rb_failed" in str(excinfo.value)
    assert state["history"] == ["s1_fw", "s2_fw", "s1_rb"]
