from pathlib import Path
from unittest.mock import Mock

from mighty_mouse.v2.engine import PolicyEngine
from mighty_mouse.v2.foundation import (
    ExecutionProfile,
    Mode,
    ModelIdentity,
    Pin,
    PolicySelection,
    Preview,
    PromotionNotice,
    Scope,
    Signal,
    TaskCategory,
)


def _inputs():
    scope = Scope(Mode.CODING, "JOHNNYMACONNY/mighty-mouse", TaskCategory.FEATURE, "local-small")
    identity = ModelIdentity("sha256:" + "a" * 64)
    profile = ExecutionProfile("codex-local", frozenset({"test"}))
    return scope, identity, profile


def test_policy_engine_controls_and_signal_delegation(tmp_path: Path) -> None:
    scope, identity, profile = _inputs()
    engine = PolicyEngine(tmp_path)
    assert engine.select_policy(scope, identity, profile).policy.policy_id == "safe-baseline-coding"
    receipt = engine.record_signal(Signal("signal-001", scope, identity.artifact_digest, profile.profile_id, "passed", 1, 0, "tests", "passed"))
    assert receipt is not None
    assert engine.get_status(scope, identity, profile)["signals"]["receipt_count"] == 1

    pin = Pin("pin-1", scope, "candidate-1", identity.artifact_digest or "", profile.profile_id)
    preview = Preview("preview-1", scope, "candidate-1", "evidence-1", identity.artifact_digest or "", profile.profile_id)
    engine._store.pin = Mock(return_value=Mock(record_hash="pin-hash"))
    engine._store.preview = Mock(return_value=PolicySelection(engine.select_policy(scope, identity, profile).policy, "preview", "test", None))
    engine._promotion_controller.promote = Mock(return_value=(Mock(record_hash="promotion-hash"), PromotionNotice("promoted", "candidate-1", "eligible_successor_passed_health_checks")))
    engine._promotion_controller.recover = Mock(return_value=PromotionNotice("rolled_back", "candidate-1", "quality_guard_failed"))

    promoted, _ = engine.promote_candidate(Mock(), identity, profile)
    assert promoted.record_hash == "promotion-hash"
    assert engine.pin(pin, identity, profile).record_hash == "pin-hash"
    assert engine.preview(preview, identity, profile).source == "preview"
    assert engine.rollback(scope, identity, profile, "test").action == "rolled_back"
    engine._store.pin.assert_called_once()
    engine._store.preview.assert_called_once()
    engine._promotion_controller.promote.assert_called_once()
    engine._promotion_controller.recover.assert_called_once()
