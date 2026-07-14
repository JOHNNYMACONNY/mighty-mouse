# AFK resource-governance verdict

Decision artifact for [Design AFK resource governance and preemption](https://github.com/JOHNNYMACONNY/mighty-mouse/issues/11). The throwaway terminal prototype that informed this verdict has been deleted; this document is the durable outcome.

## Decision

Mighty Mouse v2 makes **live improvement** available by default: ordinary use creates only the existing local, content-free Signals and queues potential improvement work. It does **not** silently begin consuming local compute merely because the machine appears idle.

The user controls **Background Research**. On a local-model machine, the user explicitly starts it when they have made resources available (for example, before leaving the computer). It runs under the selected resource mode until the user stops it, a fixed resource or disk budget is reached, or a safety guard pauses it. A user stop persists across idle periods and reboots; no automatic restart occurs without a new explicit user start.

Foreground local harness work has priority. Starting or resuming foreground work requests a safe checkpoint, pauses local Background Research, and never interrupts the active task. The paused run is visible as resumable, but it remains paused until the user starts it again. Timing evidence collected while foreground contention occurs is marked unqualified rather than used to compare Policy efficiency.

For cloud-backed Background Research, the same explicit start/stop lifecycle applies. The user may opt into a remembered per-machine preference to keep it running while using the harness because it does not require the local GPU; it is initially off and remains bounded by cost, rate, and concurrency limits. Faster local machines may later expose an explicit concurrent-research preference, but do not get a looser default safety model.

## User experience

- Default: live improvement is on; Signals accumulate privately and quietly.
- Primary control: `Start Background Research` / `Stop Background Research`.
- Status: queued, running, checkpointing, paused, stopped, or budget-blocked, with the reason and current resource mode.
- A stopped run is sticky. Restart always requires a user action.
- Promotion remains independent: only machine-gated, compatible Eligible Successors may become Champions; Background Research never bypasses Pins, Preview boundaries, or Rollback.

## Why

This keeps the harness low-friction while preserving predictable local resource use. It avoids accidental GPU-memory contention, swap pressure, battery drain, and surprise cloud cost, while still making routine user interactions useful inputs to later improvement.
