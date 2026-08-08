from pathlib import Path
from unittest.mock import Mock, call, patch

from mighty_mouse.v2.seams import PolicyMutationSurface, VerificationResult
from mutation_engine import (
    FailureAnalysis,
    MutationAttempt,
    MutationEngine,
    MutationLogRecord,
    log_mutation,
)


def _analysis(
    *,
    category: str = "LOGIC",
    timeout: bool = False,
    summary: dict[str, str] | None = None,
) -> FailureAnalysis:
    return FailureAnalysis(
        dominant_category=category,
        is_timeout_dominant=timeout,
        failures=[{"task_id": "task-1", "category": category}],
        original_summary=summary or {"success_rate": "1/1"},
    )


def _attempt(
    *,
    segment_file: str = "reasoning.txt",
    hypothesis: str = "Improve reasoning",
    new_content: str = "mutated content",
) -> MutationAttempt:
    return MutationAttempt(
        segment_file=segment_file,
        hypothesis=hypothesis,
        new_content=new_content,
    )


def _engine(
    tmp_path: Path,
    *,
    original: str = "original content",
) -> tuple[MutationEngine, Path]:
    segments_dir = tmp_path / "segments"
    segments_dir.mkdir()
    segment_path = segments_dir / "reasoning.txt"
    segment_path.write_text(original, encoding="utf-8")
    engine = MutationEngine(
        results_path=str(tmp_path / "results.json"),
        mutation_log_path=str(tmp_path / "mutation.log"),
        segments_dir=str(segments_dir),
        policy_mutation_engine=Mock(),
    )
    return engine, segment_path


def _verification(
    *,
    passed: bool,
    score: float,
    category: str = "LOGIC",
) -> VerificationResult:
    return VerificationResult(
        passed=passed,
        score=score,
        details={"verifier_category": category},
        verdict_category="PASS" if passed else "FAIL",
    )


def test_legacy_no_failures_calls_analyze_failures_and_returns_none(
    tmp_path: Path,
) -> None:
    engine, _ = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=None)
    engine.generate_mutation = Mock()
    engine.run_tier = Mock()
    engine.log_mutation = Mock()

    result = engine.execute_mutation_cycle(
        current_tier="tier-1",
        replay_tiers=[],
    )

    assert result is None
    engine.analyze_failures.assert_called_once_with()
    engine.generate_mutation.assert_not_called()
    engine.run_tier.assert_not_called()
    engine.log_mutation.assert_not_called()


def test_typed_pass_skips_legacy_analysis_and_returns_none(
    tmp_path: Path,
) -> None:
    engine, _ = _engine(tmp_path)
    engine.analyze_failures = Mock()
    engine.generate_mutation = Mock()
    engine.run_tier = Mock()
    engine.log_mutation = Mock()

    result = engine.execute_mutation_cycle(
        current_tier="tier-1",
        replay_tiers=[],
        verification_result=_verification(passed=True, score=1.0),
    )

    assert result is None
    engine.analyze_failures.assert_not_called()
    engine.generate_mutation.assert_not_called()
    engine.run_tier.assert_not_called()
    engine.log_mutation.assert_not_called()


def test_typed_failure_preserves_existing_mapping(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    engine.analyze_failures = Mock()
    engine.generate_mutation = Mock(return_value=(None, None))
    engine.log_mutation = Mock()

    record = engine.execute_mutation_cycle(
        current_tier="tier-2",
        replay_tiers=["tier-1"],
        verification_result=_verification(
            passed=False,
            score=0.25,
            category="scope",
        ),
    )

    assert record is not None
    assert record.decision == "FAILED_GENERATION"
    assert record.failure_category == "SCOPE"
    assert record.before == {"success_rate": "25/100"}
    engine.analyze_failures.assert_not_called()
    engine.generate_mutation.assert_called_once_with(
        "SCOPE",
        [
            {
                "task_id": "tier-2",
                "reason": "typed verification failure",
                "category": "SCOPE",
            }
        ],
    )


def test_timeout_freeze_logs_once_without_generation_or_segment_or_tier(
    tmp_path: Path,
) -> None:
    engine, _ = _engine(tmp_path)
    engine.analyze_failures = Mock(
        return_value=_analysis(category="TIMEOUT", timeout=True)
    )
    engine.generate_mutation = Mock()
    engine.run_tier = Mock()
    engine.log_mutation = Mock()

    with patch("builtins.open") as open_mock:
        record = engine.execute_mutation_cycle(
            current_tier="tier-1",
            replay_tiers=["tier-0"],
        )

    assert record is not None
    assert record.decision == "FROZEN_TIMEOUT"
    engine.generate_mutation.assert_not_called()
    engine.run_tier.assert_not_called()
    engine.log_mutation.assert_called_once_with(record)
    open_mock.assert_not_called()


def test_generation_failure_logs_once_without_segment_or_tier_effects(
    tmp_path: Path,
) -> None:
    engine, _ = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=(None, None))
    engine.run_tier = Mock()
    engine.log_mutation = Mock()

    with patch("builtins.open") as open_mock:
        record = engine.execute_mutation_cycle(
            current_tier="tier-1",
            replay_tiers=[],
        )

    assert record is not None
    assert record.decision == "FAILED_GENERATION"
    assert record.segment_changed == "unknown"
    engine.run_tier.assert_not_called()
    engine.log_mutation.assert_called_once_with(record)
    open_mock.assert_not_called()


def test_explicit_surface_rejection_occurs_before_segment_io(
    tmp_path: Path,
) -> None:
    engine, _ = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    engine.run_tier = Mock()
    engine.log_mutation = Mock()

    with patch("builtins.open") as open_mock:
        record = engine.execute_mutation_cycle(
            current_tier="tier-1",
            replay_tiers=[],
            mutation_surface={
                "allowed_segments": frozenset({"discipline.txt"})
            },
        )

    assert record is not None
    assert record.decision == "REJECT"
    engine.run_tier.assert_not_called()
    engine.log_mutation.assert_called_once_with(record)
    open_mock.assert_not_called()


def test_none_mutation_surface_preserves_unrestricted_legacy_path(
    tmp_path: Path,
) -> None:
    engine, segment_path = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    engine.run_tier = Mock(return_value={"success_rate": "1/1"})
    engine.log_mutation = Mock()

    record = engine.execute_mutation_cycle(
        current_tier="tier-1",
        replay_tiers=[],
        mutation_surface=None,
    )

    assert record is not None
    assert record.decision == "PROMOTE"
    assert segment_path.read_text(encoding="utf-8") == "mutated content"
    engine.run_tier.assert_called_once_with("tier-1")


def test_policy_mutation_surface_object_remains_runtime_compatible(
    tmp_path: Path,
) -> None:
    engine, _ = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    engine.run_tier = Mock()
    engine.log_mutation = Mock()
    surface = PolicyMutationSurface(frozenset({"discipline.txt"}))

    with patch("builtins.open") as open_mock:
        record = engine.execute_mutation_cycle(
            current_tier="tier-1",
            replay_tiers=[],
            mutation_surface=surface,
        )

    assert record is not None
    assert record.decision == "REJECT"
    engine.run_tier.assert_not_called()
    open_mock.assert_not_called()


def test_current_tier_regression_restores_exact_original_and_skips_replay(
    tmp_path: Path,
) -> None:
    engine, segment_path = _engine(tmp_path, original="original\n")
    engine.analyze_failures = Mock(
        return_value=_analysis(summary={"success_rate": "2/2"})
    )
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    events: list[tuple[str, str]] = []

    def run_tier(tier: str) -> dict[str, str]:
        events.append(("tier", tier))
        return {"success_rate": "1/2"}

    engine.run_tier = Mock(side_effect=run_tier)
    engine.log_mutation = Mock(
        side_effect=lambda _record: events.append(
            ("log", segment_path.read_text(encoding="utf-8"))
        )
    )

    record = engine.execute_mutation_cycle(
        current_tier="tier-2",
        replay_tiers=["tier-1"],
    )

    assert record is not None
    assert record.decision == "REJECT"
    assert segment_path.read_text(encoding="utf-8") == "original\n"
    engine.run_tier.assert_called_once_with("tier-2")
    assert events == [("tier", "tier-2"), ("log", "original\n")]


def test_equal_current_tier_rate_enters_replay_phase(tmp_path: Path) -> None:
    engine, _ = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    tiers: list[str] = []

    def run_tier(tier: str) -> dict[str, str]:
        tiers.append(tier)
        return {"success_rate": "1/1"}

    engine.run_tier = Mock(side_effect=run_tier)
    engine.log_mutation = Mock()

    record = engine.execute_mutation_cycle(
        current_tier="tier-2",
        replay_tiers=["tier-1"],
    )

    assert record is not None
    assert record.decision == "PROMOTE"
    assert tiers == ["tier-2", "tier-1"]


def test_replay_runs_in_supplied_order_and_stops_on_first_below_90(
    tmp_path: Path,
) -> None:
    engine, segment_path = _engine(tmp_path, original="original\n")
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    summaries = {
        "tier-2": {"success_rate": "1/1"},
        "tier-1": {"success_rate": "8/10"},
        "tier-0": {"success_rate": "1/1"},
    }
    tiers: list[str] = []

    def run_tier(tier: str) -> dict[str, str]:
        tiers.append(tier)
        return summaries[tier]

    engine.run_tier = Mock(side_effect=run_tier)
    engine.log_mutation = Mock()

    record = engine.execute_mutation_cycle(
        current_tier="tier-2",
        replay_tiers=["tier-1", "tier-0"],
    )

    assert record is not None
    assert record.decision == "REJECT"
    assert tiers == ["tier-2", "tier-1"]
    assert segment_path.read_text(encoding="utf-8") == "original\n"


def test_replay_exactly_90_percent_is_accepted(tmp_path: Path) -> None:
    engine, segment_path = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    engine.run_tier = Mock(
        side_effect=[
            {"success_rate": "1/1"},
            {"success_rate": "9/10"},
        ]
    )
    engine.log_mutation = Mock()

    record = engine.execute_mutation_cycle(
        current_tier="tier-2",
        replay_tiers=["tier-1"],
    )

    assert record is not None
    assert record.decision == "PROMOTE"
    assert segment_path.read_text(encoding="utf-8") == "mutated content"


def test_successful_replays_promote_without_restoration(
    tmp_path: Path,
) -> None:
    engine, segment_path = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    engine.run_tier = Mock(
        side_effect=[
            {"success_rate": "1/1"},
            {"success_rate": "1/1"},
            {"success_rate": "10/10"},
        ]
    )
    engine.log_mutation = Mock()

    record = engine.execute_mutation_cycle(
        current_tier="tier-2",
        replay_tiers=["tier-1", "tier-0"],
    )

    assert record is not None
    assert record.decision == "PROMOTE"
    assert segment_path.read_text(encoding="utf-8") == "mutated content"
    assert engine.run_tier.call_args_list == [
        call("tier-2"),
        call("tier-1"),
        call("tier-0"),
    ]


def test_no_replay_tiers_promotes_non_regressing_mutation(
    tmp_path: Path,
) -> None:
    engine, segment_path = _engine(tmp_path)
    engine.analyze_failures = Mock(return_value=_analysis())
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    engine.run_tier = Mock(return_value={"success_rate": "1/1"})
    engine.log_mutation = Mock()

    record = engine.execute_mutation_cycle(
        current_tier="tier-1",
        replay_tiers=[],
    )

    assert record is not None
    assert record.decision == "PROMOTE"
    assert segment_path.read_text(encoding="utf-8") == "mutated content"
    engine.run_tier.assert_called_once_with("tier-1")


def test_log_record_preserves_replay_list_and_current_tier_after_summary(
    tmp_path: Path,
) -> None:
    engine, segment_path = _engine(tmp_path)
    engine.analyze_failures = Mock(
        return_value=_analysis(summary={"success_rate": "1/1"})
    )
    engine.generate_mutation = Mock(return_value=("reasoning.txt", _attempt()))
    engine.run_tier = Mock(
        side_effect=[
            {"success_rate": "2/2"},
            {"success_rate": "8/10"},
        ]
    )
    logged: list[object] = []
    engine.log_mutation = Mock(side_effect=logged.append)

    record = engine.execute_mutation_cycle(
        current_tier="tier-2",
        replay_tiers=["tier-1", "tier-0"],
    )

    assert record is not None
    assert logged == [record]
    assert record.replay_tiers_tested == ["tier-1", "tier-0"]
    assert record.after == {"success_rate": "2/2"}
    assert segment_path.read_text(encoding="utf-8") == "original content"


def test_module_log_mutation_wrapper_defaults_timestamp() -> None:
    logged: list[object] = []

    with patch.object(
        MutationEngine,
        "log_mutation",
        side_effect=logged.append,
    ):
        log_mutation(
            {
                "failure_category": "LOGIC",
                "segment_changed": "reasoning.txt",
                "hypothesis": "Preserve wrapper compatibility",
                "before": {"success_rate": "1/1"},
                "after": None,
                "replay_tiers_tested": [],
                "decision": "REJECT",
            }
        )

    assert len(logged) == 1
    record = logged[0]
    assert isinstance(record, MutationLogRecord)
    assert record.timestamp
    assert record.failure_category == "LOGIC"
