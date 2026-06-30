---
name: mighty-mouse
description: Uses Mighty Mouse protocols and verification for high-reliability coding changes. Activate when the user says /mighty, asks for Mighty Mouse, or requests a complex refactor or critical bug fix.
---

# Mighty Mouse

Call the `protocol` tool in the `mcp-mighty_mouse` toolset before changing code. Choose low, medium, or high complexity from the task's real blast radius.

After editing, call `verify` in the same toolset. Provide the workspace and explicit commands if detection is incomplete. Fix failures and retry up to three times. If no meaningful check can run, report that limitation instead of declaring success.
