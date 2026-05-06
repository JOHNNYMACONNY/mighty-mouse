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

## Lesson 5 — Protocol Redundancy
**Pattern**: Double-enforcement of mandatory blocks in both `persona.txt` and `discipline.txt`.
**Why it worked**: For small-parameter models, repeating critical structural mandates (like the `<PLANNING>` block) in multiple prompt segments significantly reduces adherence failure rates.
**Conditions**: High-precision XML/JSON schema enforcement.
**Anti-pattern**: Relying on a single mention of a mandatory block in the system prompt.

## Lesson 6 — The "Helpfulness" Trap (Scope Leak)
**Pattern**: Models creating untracked test scripts for self-verification.
**Why it worked**: On Tier 3 tasks, the model became "too helpful" and wrote `test_script` or similar files to root to verify its work. While this helped pass logic tests, it triggered Scope Failures.
**Conditions**: Adversarial or complex multi-file tasks.
**Anti-pattern**: Failing to explicitly mandate a "Zero-Footprint" cleanup protocol. Note: Initial attempts to fix this by adding a "Zero-Footprint" instruction yielded shifted failures, suggesting deeper structural reinforcement is needed.
