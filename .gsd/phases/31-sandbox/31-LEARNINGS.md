---
phase: 31
phase_name: "Sandbox Integration"
project: "Mighty Mouse"
generated: "2026-05-06"
counts:
  decisions: 2
  lessons: 5
  patterns: 4
  surprises: 3
missing_artifacts:
  - "31-PLAN.md"
  - "31-VERIFICATION.md"
  - "31-UAT.md"
  - "STATE.md"
---

# Phase 31 Learnings: Sandbox Integration

## Decisions

### Native Sandbox Wrapper Implementation
Implemented `eval/sandbox_wrapper.py` using resource limits (`resource.RLIMIT_CPU` and `resource.RLIMIT_AS`) and monkey-patching `socket` and `builtins.open` to provide a high-security execution layer.

**Rationale:** To block adversarial attempts to write outside the workspace and open network connections, ensuring deterministic execution.
**Source:** SUMMARY.md

### Orchestrator Integration
Refactored `eval/run_parallel.py` to wrap the `run_benchmark.py` step inside the sandbox.

**Rationale:** To provide a "Zero-Trust" execution environment for benchmarking, isolating the host system from agent-generated code.
**Source:** SUMMARY.md

---

## Lessons

### Local Inference Hardening
Python treats imports as assignments to local names if inside functions. Using the same name (e.g., `os`) elsewhere in the function before the import causes `UnboundLocalError`.

**Context:** Discovered during high-reliability facade implementation. Relying on "just-in-time" imports without checking scope conflicts is an anti-pattern.
**Source:** autoresearch-lessons.md

### Workspace Isolation
Purging untracked files with `git clean -fd` is necessary.

**Context:** Prevents "ghost" files from previous tasks from confusing the scope verifier. Assuming `git checkout .` removes new files is an anti-pattern.
**Source:** autoresearch-lessons.md

### Manifest Metadata
Ensuring the harness config is COMMITTED is critical if the reset script performs a checkout of the `configs/` directory.

**Context:** Running experiments on uncommitted config changes while a reset script is active leads to lost mutations.
**Source:** autoresearch-lessons.md

### The "Helpfulness" Trap (Scope Leak)
Models became "too helpful" and wrote `test_script` or similar files to verify their work. While this helped pass logic tests, it triggered Scope Failures.

**Context:** Discovered during adversarial tasks. Requires explicitly mandating a "Zero-Footprint" cleanup protocol.
**Source:** autoresearch-lessons.md

### Context Window Bottleneck for Needle-in-Haystack
High-noise tasks (100KB) truncated the 8192 context window, causing strict filename adherence failure because the model never saw the expected filename at the top of the prompt.

**Context:** Discovered during Tier 7 tasks. Expanding context to 32768 resolved the issue, allowing the 9B model to succeed.
**Source:** Session Logs

---

## Patterns

### Small Model Prompting
Explicit XML-style block reminders in every prompt.

**When to use:** For low-parameter local inference models (like `gemma4:e4b`) that tend to drift into conversational mode or forget strict output schemas.
**Source:** autoresearch-lessons.md

### Protocol Redundancy
Double-enforcement of mandatory blocks in both `persona.txt` and `discipline.txt`.

**When to use:** To significantly reduce adherence failure rates for small-parameter models by repeating critical structural mandates.
**Source:** autoresearch-lessons.md

### Mental De-noising
Explicitly instructing the model: "If you write tests for internal verification, you MUST do so purely in your mind... NEVER output them as code blocks."

**When to use:** To prevent unauthorized file creation and solve the "Helpfulness Trap" without sacrificing the model's internal verification logic.
**Source:** Session Logs / constraints.txt mutation

### Strict Filename Adherence
Forcing exact string matches: "You MUST use the exact filenames listed... Hallucinating alternate filenames is a CRITICAL failure."

**When to use:** To combat large context (100KB) noise and force the model to anchor to exact required file paths.
**Source:** Session Logs / constraints.txt mutation

---

## Surprises

### Autonomous System Self-Correction
The autoresearch loop was able to autonomously diagnose its own "helpfulness trap" and write the "Zero-Footprint" policy and "Mental De-noising" rules without human intervention.

**Impact:** Proved the capability of the perpetual harness to self-heal its own prompts to bypass structural failures.
**Source:** Session Logs

### Shifted Failures
Initial attempts to fix the helpfulness trap by adding a simple "Zero-Footprint" instruction yielded shifted failures.

**Impact:** Revealed that deeper structural reinforcement (Protocol Redundancy and Mental De-noising) was needed to fully correct behavior.
**Source:** autoresearch-lessons.md

### 9B Model Competence at 32k Context
Tier 7 Needle-in-Haystack tasks (100KB+ / 30,000 tokens) were successfully parsed by a 9B model (`gemma4:e4b`).

**Impact:** Once the context limit was bumped to 32k, the model achieved a 100% success rate on Tier 7, exceeding expectations for its parameter size.
**Source:** Session Logs
