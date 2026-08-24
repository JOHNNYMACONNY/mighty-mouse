"""Canonical Host Hook Contract v1.

Provides typed, immutable, host-independent lifecycle event and result models.
Enforces the core architectural invariant: host payload != authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Literal

from mighty_mouse.host.adapter import AdapterRuntimeContext

HOST_HOOK_SCHEMA_VERSION = 1

HostHookPhase = Literal[
    "pre_action",
    "post_action",
    "post_task",
]
VALID_HOST_HOOK_PHASES = frozenset({"pre_action", "post_action", "post_task"})

HostHookActionKind = Literal[
    "file_write",
    "file_delete",
    "shell_command",
    "other",
]
VALID_HOST_HOOK_ACTION_KINDS = frozenset(
    {"file_write", "file_delete", "shell_command", "other"}
)

HostHookMutationClass = Literal[
    "read_only",
    "workspace_mutation",
    "repository_mutation",
    "unknown",
]
VALID_HOST_HOOK_MUTATION_CLASSES = frozenset(
    {"read_only", "workspace_mutation", "repository_mutation", "unknown"}
)

HookDisposition = Literal[
    "allow",
    "deny",
    "continue",
    "retry",
    "abort",
]
VALID_HOOK_DISPOSITIONS = frozenset(
    {"allow", "deny", "continue", "retry", "abort"}
)

HookRecoveryExecutionMode = Literal["agent", "swarm"]
VALID_HOOK_RECOVERY_EXECUTION_MODES = frozenset({"agent", "swarm"})

VALID_REASON_CODES = frozenset(
    {
        "not_applicable",
        "malformed_event",
        "unsupported_phase",
        "unsupported_action",
        "invalid_workspace",
        "runtime_context_unavailable",
        "verification_passed",
        "verification_failed",
        "recovery_not_enabled",
        "recovery_succeeded",
        "recovery_failed",
        "retry_budget_exhausted",
        "recursive_hook_suppressed",
        "internal_error",
    }
)


def _validate_schema_version(schema_version: Any) -> None:
    """Validate schema version strictly as non-bool int equal to 1."""
    if (
        isinstance(schema_version, bool)
        or not isinstance(schema_version, int)
        or schema_version != HOST_HOOK_SCHEMA_VERSION
    ):
        raise ValueError(
            f"Unsupported host hook schema version: {schema_version}"
        )


def _validate_closed_vocabulary(
    value: Any, valid_set: frozenset[str], name: str
) -> None:
    """Validate membership in closed vocabulary rejecting non-strings."""
    if not isinstance(value, str) or value not in valid_set:
        raise ValueError(f"Invalid {name}: {value}")


def normalize_target_paths(paths: Any) -> tuple[str, ...]:
    """Normalize, canonicalize, and validate relative workspace paths."""
    if not isinstance(paths, (tuple, list)):
        raise ValueError("target_paths must be a sequence of path strings")
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in paths:
        if not isinstance(raw, str):
            raise ValueError("target_paths entries must be strings")
        trimmed = raw.strip()
        if not trimmed:
            raise ValueError("target_paths entry cannot be empty")
        # Check POSIX root or Windows root/UNC/drive prefixes
        if (
            trimmed.startswith("/")
            or trimmed.startswith("\\")
            or trimmed.startswith("//")
            or trimmed.startswith(r"\\")
        ):
            raise ValueError(f"target_paths entry cannot be absolute: {raw}")
        win_pure = PureWindowsPath(trimmed)
        if win_pure.is_absolute() or win_pure.drive or win_pure.root:
            raise ValueError(f"target_paths entry cannot be absolute: {raw}")
        if ".." in win_pure.parts:
            raise ValueError(
                "target_paths entry cannot contain parent traversal '..': "
                f"{raw}"
            )
        posix_pure = PurePosixPath(trimmed.replace("\\", "/"))
        if posix_pure.is_absolute():
            raise ValueError(f"target_paths entry cannot be absolute: {raw}")
        if ".." in posix_pure.parts:
            raise ValueError(
                "target_paths entry cannot contain parent traversal '..': "
                f"{raw}"
            )
        posix_str = posix_pure.as_posix()
        if posix_str not in seen:
            seen.add(posix_str)
            normalized.append(posix_str)
    return tuple(normalized)


@dataclass(frozen=True)
class HostHookAction:
    """Normalized observable host action description."""

    kind: HostHookActionKind
    mutation_class: HostHookMutationClass
    target_paths: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _validate_closed_vocabulary(
            self.kind, VALID_HOST_HOOK_ACTION_KINDS, "host hook action kind"
        )
        _validate_closed_vocabulary(
            self.mutation_class,
            VALID_HOST_HOOK_MUTATION_CLASSES,
            "host hook mutation class",
        )
        norm_paths = normalize_target_paths(self.target_paths)
        if norm_paths != self.target_paths:
            object.__setattr__(self, "target_paths", norm_paths)


@dataclass(frozen=True)
class HostHookEvent:
    """Normalized host lifecycle event (non-authoritative)."""

    schema_version: int
    event_id: str
    phase: HostHookPhase
    workspace: str
    action: HostHookAction
    source: str
    session_id: str | None = None

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        _validate_closed_vocabulary(
            self.phase, VALID_HOST_HOOK_PHASES, "host hook phase"
        )
        if not isinstance(self.workspace, str) or not self.workspace.strip():
            raise ValueError("workspace must be a non-empty string")
        if not isinstance(self.action, HostHookAction):
            raise ValueError("action must be an instance of HostHookAction")
        if not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("source must be a non-empty string")
        if self.session_id is not None:
            if not isinstance(self.session_id, str):
                raise ValueError("session_id must be a string if provided")


@dataclass(frozen=True)
class ResolvedHostHookEvent:
    """HostHookEvent coupled with authoritative canonical runtime context."""

    event: HostHookEvent
    runtime_context: AdapterRuntimeContext

    def __post_init__(self) -> None:
        if not isinstance(self.event, HostHookEvent):
            raise ValueError("event must be a HostHookEvent instance")
        if not isinstance(self.runtime_context, AdapterRuntimeContext):
            raise ValueError(
                "runtime_context must be an AdapterRuntimeContext instance"
            )


@dataclass(frozen=True)
class HookVerificationSummary:
    """Bounded, privacy-safe summary of canonical verification."""

    occurred: bool
    passed: bool | None
    summary: str

    def __post_init__(self) -> None:
        if not isinstance(self.occurred, bool):
            raise ValueError("occurred must be a boolean")
        if self.passed is not None and not isinstance(self.passed, bool):
            raise ValueError("passed must be a boolean or None")
        if not isinstance(self.summary, str):
            raise ValueError("summary must be a string")


@dataclass(frozen=True)
class HookRecoverySummary:
    """Bounded, privacy-safe summary of self-healing recovery."""

    attempted: bool
    succeeded: bool | None
    attempts: int
    execution_mode: HookRecoveryExecutionMode | None

    def __post_init__(self) -> None:
        if not isinstance(self.attempted, bool):
            raise ValueError("attempted must be a boolean")
        if self.succeeded is not None and not isinstance(self.succeeded, bool):
            raise ValueError("succeeded must be a boolean or None")
        if (
            isinstance(self.attempts, bool)
            or not isinstance(self.attempts, int)
            or self.attempts < 0
        ):
            raise ValueError("attempts must be a non-negative integer")
        if self.execution_mode is not None:
            _validate_closed_vocabulary(
                self.execution_mode,
                VALID_HOOK_RECOVERY_EXECUTION_MODES,
                "recovery execution mode",
            )


@dataclass(frozen=True)
class HostHookResult:
    """Bounded result envelope returned to host adapters."""

    schema_version: int
    event_id: str
    disposition: HookDisposition
    reason_code: str
    summary: str
    verification: HookVerificationSummary | None = None
    recovery: HookRecoverySummary | None = None

    def __post_init__(self) -> None:
        _validate_schema_version(self.schema_version)
        if not isinstance(self.event_id, str) or not self.event_id.strip():
            raise ValueError("event_id must be a non-empty string")
        _validate_closed_vocabulary(
            self.disposition, VALID_HOOK_DISPOSITIONS, "hook disposition"
        )
        _validate_closed_vocabulary(
            self.reason_code, VALID_REASON_CODES, "hook reason_code"
        )
        if not isinstance(self.summary, str):
            raise ValueError("summary must be a string")
        if self.verification is not None and not isinstance(
            self.verification, HookVerificationSummary
        ):
            raise ValueError(
                "verification must be HookVerificationSummary or None"
            )
        if self.recovery is not None and not isinstance(
            self.recovery, HookRecoverySummary
        ):
            raise ValueError("recovery must be HookRecoverySummary or None")
