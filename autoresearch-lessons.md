# Autoresearch Lessons - Mighty Mouse Harness

## Lesson 1 — Local Inference Hardening
**Pattern**: Nested imports inside class methods or loops.
**Why it worked**: Python treats imports as assignments to local names if they are inside functions. If the same name (e.g., `os`) is used elsewhere in the function before the import, it causes `UnboundLocalError`.
**Conditions**: High-reliability facades with multiple providers.
**Anti-pattern**: Relying on "just-in-time" imports without checking scope conflicts.

## Lesson 2 — Workspace Isolation
**Pattern**: Purging untracked files with `git clean -fd`.
**Why it worked**: Prevents "ghost" files from previous tasks from confusing the scope verifier.
**Conditions**: Parallel or sequential benchmark runs in a shared directory.
**Anti-pattern**: Assuming `git checkout .` removes new files (it doesn't).

## Lesson 3 — Manifest Metadata
**Pattern**: `git checkout -- .` reverts all uncommitted changes.
**Why it worked**: Ensuring the harness config is COMMITTED is critical if the reset script performs a checkout of the `configs/` directory.
**Conditions**: Automated loops that perform workspace resets.
**Anti-pattern**: Running experiments on uncommitted config changes while a reset script is active.

## Lesson 4 — Small Model Prompting (Gemma 4)
**Pattern**: Explicit XML-style block reminders in every prompt.
**Why it worked**: Smaller models like `gemma4:e4b` tend to drift into conversational mode or forget the strict output schema (fenced code blocks with paths) without constant reinforcement.
**Conditions**: Low-parameter local inference.
**Anti-pattern**: Assuming the model will remember the system prompt instructions for complex tasks.
