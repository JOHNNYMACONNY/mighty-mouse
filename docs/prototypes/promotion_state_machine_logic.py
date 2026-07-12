"""Throwaway prototype logic for Mighty Mouse v2 promotion-state decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field


@dataclass
class PromotionState:
    active_champion: str = "champion-v1"
    previous_eligible: str | None = None
    candidate: str = "candidate-v2"
    eligible_successor: str | None = None
    pin: str | None = None
    preview: str | None = None
    auto_enabled: bool = True
    history: list[str] = field(default_factory=lambda: ["champion-v1"])
    events: list[str] = field(default_factory=list)


def reduce(state: PromotionState, action: str) -> PromotionState:
    """Apply one state-machine action without terminal I/O."""
    next_state = PromotionState(**asdict(state))

    if action == "promote":
        if not next_state.auto_enabled:
            next_state.events.append("promotion blocked: auto is paused")
        elif next_state.pin:
            next_state.eligible_successor = next_state.candidate
            next_state.events.append("candidate verified as eligible successor; pin keeps champion unchanged")
        else:
            next_state.previous_eligible = next_state.active_champion
            next_state.active_champion = next_state.candidate
            next_state.history.append(next_state.candidate)
            next_state.events.append("candidate promoted; post-promotion guard is now active")
    elif action == "guard_fail":
        if next_state.previous_eligible:
            failed = next_state.active_champion
            next_state.active_champion = next_state.previous_eligible
            next_state.previous_eligible = None
            next_state.auto_enabled = False
            next_state.events.append(f"guard failed for {failed}; rolled back and paused auto")
        else:
            next_state.events.append("guard failure needs recovery: no previous eligible champion")
    elif action == "pin":
        next_state.pin = next_state.active_champion
        next_state.events.append(f"pinned {next_state.pin}")
    elif action == "unpin":
        next_state.events.append(f"removed pin {next_state.pin or 'none'}")
        next_state.pin = None
    elif action == "revalidate_successor":
        if next_state.pin:
            next_state.events.append("successor gate blocked: pin still applies")
        elif not next_state.eligible_successor:
            next_state.events.append("successor gate skipped: no eligible successor")
        else:
            next_state.previous_eligible = next_state.active_champion
            next_state.active_champion = next_state.eligible_successor
            next_state.history.append(next_state.eligible_successor)
            next_state.eligible_successor = None
            next_state.events.append("successor revalidated and promoted; post-promotion guard is active")
    elif action == "preview":
        next_state.preview = next_state.candidate
        next_state.events.append(f"previewing {next_state.preview}; champion unchanged")
    elif action == "end_preview":
        next_state.events.append(f"ended preview {next_state.preview or 'none'}")
        next_state.preview = None
    elif action == "manual_rollback":
        if next_state.previous_eligible:
            current = next_state.active_champion
            next_state.active_champion, next_state.previous_eligible = next_state.previous_eligible, current
            next_state.events.append(f"manual rollback to {next_state.active_champion}")
        else:
            next_state.events.append("manual rollback unavailable: no previous eligible champion")
    elif action == "resume_auto":
        next_state.auto_enabled = True
        next_state.events.append("auto promotion resumed")
    else:
        next_state.events.append(f"unknown action: {action}")

    return next_state
