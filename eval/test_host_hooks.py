"""Tests for canonical Host Hook Contract v1 (pure/non-mutating)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from pathlib import Path
import pytest

from mighty_mouse.host.adapter import (
    AdapterRuntimeContext,
    ExecutionProfile,
    ModelIdentity,
)
from mighty_mouse.host.hooks import (
    HookRecoverySummary,
    HookVerificationSummary,
    HostHookAction,
    HostHookEvent,
    HostHookResult,
    ResolvedHostHookEvent,
    VALID_HOOK_DISPOSITIONS,
    VALID_HOOK_RECOVERY_EXECUTION_MODES,
    VALID_HOST_HOOK_ACTION_KINDS,
    VALID_HOST_HOOK_MUTATION_CLASSES,
    VALID_HOST_HOOK_PHASES,
    VALID_REASON_CODES,
    normalize_target_paths,
)


def _dummy_runtime_context() -> AdapterRuntimeContext:
    profile = ExecutionProfile(
        profile_id="prof-123",
        runtime_kind="antigravity",
        runtime_version="1.0.0",
        effective_context_limit=32000,
        tool_contract_digest="sha256:abc",
        prompt_template_digest="sha256:def",
        sampling_settings={},
        resource_limits={},
        capabilities=frozenset({"mcp"}),
    )
    return AdapterRuntimeContext(
        state_dir=Path("/fake/workspace/.mighty-mouse"),
        repository="test-org/test-repo",
        model_class="gemma-27b",
        model_identity=ModelIdentity(artifact_digest="sha256:111"),
        execution_profile=profile,
        model_source="host",
    )


def test_contract_dataclasses_frozen() -> None:
    """All hook contract data structures must be frozen dataclasses."""
    action = HostHookAction(
        kind="file_write", mutation_class="workspace_mutation"
    )
    with pytest.raises(FrozenInstanceError):
        action.kind = "file_delete"  # type: ignore[misc]

    event = HostHookEvent(
        schema_version=1,
        event_id="evt-1",
        phase="pre_action",
        workspace="/test/ws",
        action=action,
        source="test_runner",
    )
    with pytest.raises(FrozenInstanceError):
        event.workspace = "/other"  # type: ignore[misc]

    resolved = ResolvedHostHookEvent(
        event=event,
        runtime_context=_dummy_runtime_context(),
    )
    with pytest.raises(FrozenInstanceError):
        resolved.event = event  # type: ignore[misc]

    verif = HookVerificationSummary(
        occurred=True, passed=True, summary="pass"
    )
    with pytest.raises(FrozenInstanceError):
        verif.passed = False  # type: ignore[misc]

    rec = HookRecoverySummary(
        attempted=True,
        succeeded=True,
        attempts=1,
        execution_mode="agent",
    )
    with pytest.raises(FrozenInstanceError):
        rec.attempts = 2  # type: ignore[misc]

    res = HostHookResult(
        schema_version=1,
        event_id="evt-1",
        disposition="allow",
        reason_code="not_applicable",
        summary="ok",
    )
    with pytest.raises(FrozenInstanceError):
        res.disposition = "deny"  # type: ignore[misc]


def test_strict_schema_version_typing() -> None:
    """Strict schema version check: 1 ok, bool/float/str rejected."""
    action = HostHookAction(
        kind="file_write", mutation_class="workspace_mutation"
    )

    # 1 accepted
    evt = HostHookEvent(
        schema_version=1,
        event_id="evt-1",
        phase="pre_action",
        workspace="/test/ws",
        action=action,
        source="test_runner",
    )
    assert evt.schema_version == 1

    # True / False rejected
    for bad_ver in (True, False, 1.0, 2, 0, "1", None, [1]):
        with pytest.raises(
            ValueError, match="Unsupported host hook schema version"
        ):
            HostHookEvent(
                schema_version=bad_ver,  # type: ignore[arg-type]
                event_id="evt-1",
                phase="pre_action",
                workspace="/test/ws",
                action=action,
                source="test_runner",
            )

        with pytest.raises(
            ValueError, match="Unsupported host hook schema version"
        ):
            HostHookResult(
                schema_version=bad_ver,  # type: ignore[arg-type]
                event_id="evt-1",
                disposition="allow",
                reason_code="not_applicable",
                summary="ok",
            )


def test_closed_vocabularies() -> None:
    """All closed vocabularies accept valid strings and raise ValueError."""
    for phase in VALID_HOST_HOOK_PHASES:
        event = HostHookEvent(
            schema_version=1,
            event_id="evt-1",
            phase=phase,  # type: ignore[arg-type]
            workspace="/ws",
            action=HostHookAction(kind="other", mutation_class="read_only"),
            source="test",
        )
        assert event.phase == phase

    for bad_phase in ("unknown_phase", 123, True, ["pre_action"], None, {}):
        with pytest.raises(ValueError, match="Invalid host hook phase"):
            HostHookEvent(
                schema_version=1,
                event_id="evt-1",
                phase=bad_phase,  # type: ignore[arg-type]
                workspace="/ws",
                action=HostHookAction(
                    kind="other", mutation_class="read_only"
                ),
                source="test",
            )

    for kind in VALID_HOST_HOOK_ACTION_KINDS:
        act = HostHookAction(
            kind=kind, mutation_class="read_only"  # type: ignore[arg-type]
        )
        assert act.kind == kind

    for bad_kind in ("unsupported_kind", 999, False, ("file_write",), None):
        with pytest.raises(ValueError, match="Invalid host hook action kind"):
            HostHookAction(
                kind=bad_kind,  # type: ignore[arg-type]
                mutation_class="read_only",
            )

    for mc in VALID_HOST_HOOK_MUTATION_CLASSES:
        act = HostHookAction(
            kind="other", mutation_class=mc  # type: ignore[arg-type]
        )
        assert act.mutation_class == mc

    for bad_mc in ("forbidden_class", 1.5, True, ["read_only"], None):
        with pytest.raises(
            ValueError, match="Invalid host hook mutation class"
        ):
            HostHookAction(
                kind="other",
                mutation_class=bad_mc,  # type: ignore[arg-type]
            )

    for disp in VALID_HOOK_DISPOSITIONS:
        res = HostHookResult(
            schema_version=1,
            event_id="evt-1",
            disposition=disp,  # type: ignore[arg-type]
            reason_code="not_applicable",
            summary="test",
        )
        assert res.disposition == disp

    for bad_disp in ("invalid_disp", 0, True, ["allow"], None):
        with pytest.raises(ValueError, match="Invalid hook disposition"):
            HostHookResult(
                schema_version=1,
                event_id="evt-1",
                disposition=bad_disp,  # type: ignore[arg-type]
                reason_code="not_applicable",
                summary="test",
            )

    for rc in VALID_REASON_CODES:
        res = HostHookResult(
            schema_version=1,
            event_id="evt-1",
            disposition="allow",
            reason_code=rc,
            summary="test",
        )
        assert res.reason_code == rc

    for bad_rc in ("unknown_code", 404, False, {"rc": "test"}, None):
        with pytest.raises(ValueError, match="Invalid hook reason_code"):
            HostHookResult(
                schema_version=1,
                event_id="evt-1",
                disposition="allow",
                reason_code=bad_rc,  # type: ignore[arg-type]
                summary="test",
            )

    for mode in VALID_HOOK_RECOVERY_EXECUTION_MODES:
        rec = HookRecoverySummary(
            attempted=True,
            succeeded=True,
            attempts=1,
            execution_mode=mode,  # type: ignore[arg-type]
        )
        assert rec.execution_mode == mode

    for bad_mode in ("invalid_mode", 1, True, ["agent"]):
        with pytest.raises(
            ValueError, match="Invalid recovery execution mode"
        ):
            HookRecoverySummary(
                attempted=True,
                succeeded=True,
                attempts=1,
                execution_mode=bad_mode,  # type: ignore[arg-type]
            )

    # Attempts validation
    for bad_attempts in (True, False, -1, 1.5, "1"):
        with pytest.raises(
            ValueError, match="attempts must be a non-negative integer"
        ):
            HookRecoverySummary(
                attempted=True,
                succeeded=True,
                attempts=bad_attempts,  # type: ignore[arg-type]
                execution_mode="agent",
            )


def test_path_normalization_and_rejection() -> None:
    """Relative paths normalized; invalid rejected across OS formats."""
    # Valid relative paths
    norm = normalize_target_paths(["src/file1.py", "tests/test_x.py"])
    assert norm == ("src/file1.py", "tests/test_x.py")

    # Empty tuple accepted
    assert normalize_target_paths([]) == ()

    # Deduplication and deterministic order across forward and backslashes
    norm_dup = normalize_target_paths(
        [r"src\pkg\a.py", "src/pkg/a.py", r"src\b.py"]
    )
    assert norm_dup == ("src/pkg/a.py", "src/b.py")

    # POSIX absolute paths
    with pytest.raises(ValueError, match="cannot be absolute"):
        normalize_target_paths(["/etc/passwd"])

    # Windows rooted paths
    with pytest.raises(ValueError, match="cannot be absolute"):
        normalize_target_paths([r"\Windows\System32"])

    # Windows drive absolute with backslashes
    with pytest.raises(ValueError, match="cannot be absolute"):
        normalize_target_paths([r"C:\Windows\System32"])

    # Windows drive absolute with forward slashes
    with pytest.raises(ValueError, match="cannot be absolute"):
        normalize_target_paths(["C:/Windows/System32"])

    # Windows drive-relative
    with pytest.raises(ValueError, match="cannot be absolute"):
        normalize_target_paths([r"C:relative\file.py"])

    # Windows UNC path
    with pytest.raises(ValueError, match="cannot be absolute"):
        normalize_target_paths([r"\\server\share\file.py"])

    # POSIX parent traversal
    with pytest.raises(ValueError, match="parent traversal"):
        normalize_target_paths(["src/../../secret.txt"])

    # Windows parent traversal
    with pytest.raises(ValueError, match="parent traversal"):
        normalize_target_paths([r"src\..\secret.txt"])

    # Rejection of empty entries
    with pytest.raises(ValueError, match="cannot be empty"):
        normalize_target_paths(["  "])

    # Rejection of non-string entries
    with pytest.raises(ValueError, match="must be strings"):
        normalize_target_paths([123])  # type: ignore[list-item]


def test_resolved_host_hook_event_requires_runtime_context() -> None:
    """ResolvedHostHookEvent requires typed AdapterRuntimeContext."""
    event = HostHookEvent(
        schema_version=1,
        event_id="evt-1",
        phase="post_action",
        workspace="/test/ws",
        action=HostHookAction(
            kind="file_write", mutation_class="workspace_mutation"
        ),
        source="test",
    )
    ctx = _dummy_runtime_context()
    resolved = ResolvedHostHookEvent(event=event, runtime_context=ctx)
    assert resolved.event == event
    assert resolved.runtime_context == ctx

    with pytest.raises(
        ValueError, match="must be an AdapterRuntimeContext instance"
    ):
        ResolvedHostHookEvent(
            event=event,
            runtime_context={"fake": "dict"},  # type: ignore[arg-type]
        )


def test_event_has_no_caller_authority_fields() -> None:
    """HostHookEvent must not expose authority fields."""
    event_fields = set(HostHookEvent.__dataclass_fields__.keys())
    forbidden = {
        "model_digest",
        "model_name",
        "execution_profile",
        "execution_profile_id",
        "state_dir",
        "policy_id",
        "scaling_pin_id",
        "application_adapter",
        "verification_adapter",
        "metadata",
        "extra",
    }
    assert not (event_fields & forbidden)
