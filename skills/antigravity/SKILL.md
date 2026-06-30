---
name: mighty-mouse
description: Applies a verification-driven coding protocol to complex code changes. Use for multi-file refactors, difficult bug fixes, critical paths, or when the user invokes /mighty or asks to use Mighty Mouse.
---

# Mighty Mouse

1. Call `mighty-mouse/protocol` with the task description and `low`, `medium`, or `high` complexity.
2. Follow the returned protocol while inspecting and changing the workspace.
3. Call `mighty-mouse/verify` after editing. Pass explicit test, lint, or build commands when auto-detection is insufficient, and pass `allowed_paths` when scope is constrained.
4. If verification fails, use its output and suggestions to fix the root cause, then verify again. Stop after three failed rounds and report the remaining blocker.
5. Never convert an unverified result into a completion claim.

Manual trigger: `/mighty` or “use the Mighty Mouse protocol.”
