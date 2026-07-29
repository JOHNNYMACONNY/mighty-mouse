---
name: autonomous-delivery
description: "Workspace-specific stateful controller for one-command software delivery with per-run state, capability discovery, evidence-based readiness, and Antigravity compatibility checks."
---

# Autonomous Delivery Controller

`autonomous-delivery` is the stateful controller governing automated software delivery in this repository. It operates from a natural-language request through mode selection, per-run state creation, plan validation, TDD implementation, UI verification, code review, targeted repair, and final integration.

## 1. Skill Integration & Orchestration Rules

This controller orchestrates the following exact installed skills without modifying, duplicating, or replacing them:

- `implement`: (`/Users/bobbyinthelobby/.gemini/config/skills/implement/SKILL.md`) - Executes feature/bug implementation. **Note**: `implement` already invokes `tdd` internally at pre-agreed seams and invokes `code-review` upon completion.
- `tdd`: (`/Users/bobbyinthelobby/.gemini/config/skills/tdd/SKILL.md`) - Reference for red-green-refactor loop at public seams.
- `code-review`: (`/Users/bobbyinthelobby/.gemini/config/skills/code-review/SKILL.md`) - Two-axis review (Standards & Spec) using parallel sub-agents against baseline `HEAD`.
- `diagnosing-bugs`: (`/Users/bobbyinthelobby/.gemini/config/skills/diagnosing-bugs/SKILL.md`) - Diagnosis loop for hard/intermittent bugs and performance regressions.
- `validate-implementation-plan`: (`.agents/skills/validate-implementation-plan/SKILL.md`) - Independent plan validator.

### Anti-Duplicate Orchestration Policy
- Because `implement` already invokes `tdd` and `code-review` internally, the controller MUST capture and interpret the review findings returned directly by `implement`.
- An explicit additional `code-review` call MUST be run ONLY:
  1. After repair iterations are applied,
  2. For final integration review before completion, or
  3. If the review inside `implement` failed or was skipped.
- Do NOT repeatedly run an unchanged `code-review` against an unchanged git diff.

---

## 2. Mode Selection & Ticket Policy

Mode selection is automatic based on repository inspection. Do NOT prompt the user to pick a mode.

### Mode Classification Criteria
- **FAST**: Localized, single-file or tight multi-file change with clear behavior; existing test seam available; no migrations, public APIs, authentication/security changes, or structural architecture changes.
- **STANDARD**: Bounded feature or bug fix touching multiple files/components; UI behavior requiring browser verification; limited reversible design choices.
- **DEEP**: New subsystem, architectural refactoring, database migrations, public API changes, authentication/security/privacy changes, or substantial unresolved uncertainty.
- **Auto-Escalation**: If inspection during planning reveals hidden API, schema, or architectural changes, automatically escalate mode (`FAST` -> `STANDARD` or `STANDARD` -> `DEEP`) and log the rationale in `state.yaml`.

### Ticket Policy
- **FAST**: NEVER create a tracker ticket unless the request already explicitly references an existing ticket (e.g. `#123`).
- **STANDARD**: Use internal run artifacts (`plan.md`, `decisions.md`) by default. Create or modify a tracker ticket ONLY if the user explicitly requests it or the task originated from an existing ticket.
- **DEEP**: Tracker use is permitted when it materially improves coordination. Keep decision work and implementation work separate. NEVER create tickets merely to document that another ticket should be created.

---

## 3. Per-Run Resumable State & Concurrency Control

Every run MUST create a dedicated run directory under `.autonomous-delivery/runs/<run-id>/` where `<run-id>` is a timestamped or unique run ID (e.g. `run-20260728-214200`).

### Per-Run File Structure
- `.autonomous-delivery/runs/<run-id>/state.yaml` - Structured state and execution metadata.
- `.autonomous-delivery/runs/<run-id>/plan.md` - Planning artifact.
- `.autonomous-delivery/runs/<run-id>/decisions.md` - Reversible engineering decisions & assumptions log.
- `.autonomous-delivery/runs/<run-id>/findings.yaml` - Code review and test failure findings log.
- `.autonomous-delivery/active_run` - Pointer file containing the active run ID string for the single implicit active run context.

### Concurrency Rules
- `.autonomous-delivery/active_run` supports at most **ONE** implicit active run.
- Parallel or concurrent execution **MUST** explicitly pass `--run-id <run-id>` to avoid state pointer conflicts.

### State Schema (`state.yaml`)
```yaml
run_id: string
dry_run: boolean
original_request: string
selected_mode: "FAST" | "STANDARD" | "DEEP"
mode_rationale: string
current_stage: string
baseline_revision: string # Git commit SHA at start
baseline_dirty_files: list of string # Pre-existing uncommitted user files
completed_stages: list of string
pending_stages: list of string
capabilities:
  build: { status: "AVAILABLE", command: ".venv/bin/pip install -e . -e ./mcp" }
  lint: { status: "UNAVAILABLE", command: null }
  typecheck: { status: "UNAVAILABLE", command: null }
  combined_test_suite: { status: "AVAILABLE", command: ".venv/bin/pytest eval/" }
  browser_verification: { status: "AVAILABLE", tool: "chrome-devtools-mcp" }
  automated_e2e_test: { status: "UNAVAILABLE", command: null }
permissions_verified: boolean
antigravity_compatibility:
  skills_discoverable: boolean
  subagents_reachable: boolean
  browser_tools_available: boolean
  verdict: "PASSED" | "BLOCKED"
decisions_and_assumptions: list of string
test_results:
  last_exit_code: int
  summary: string
review_findings_summary:
  standards_count: int
  spec_count: int
repair_cycle_count: int # Max 6
no_progress_counter: int # Max 2
planning_cycle_count: int # Max 3
terminal_status: "IN_PROGRESS" | "COMPLETE" | "BLOCKED_NEEDS_USER" | "BLOCKED_ENVIRONMENT" | "FAILED_TO_CONVERGE"
```

---

## 4. Normalized Terminal States

The controller MUST normalize terminal states across all skills, workflows, and logs to EXACTLY these four values:

1. **`COMPLETE`**: All acceptance criteria met, build/tests pass, zero critical/major review findings, tickets updated.
2. **`BLOCKED_NEEDS_USER`**: True blocker requires explicit user intervention (contradictory requirements, ungranted permissions, irreversible destructive action, credential needed).
3. **`BLOCKED_ENVIRONMENT`**: Infrastructure failure, missing system dependency, or Antigravity compatibility gate failure.
4. **`FAILED_TO_CONVERGE`**: Exhausted 6 repair cycles, 2 consecutive no-progress cycles, or 3 failed planning cycles (`REVISE`/`BLOCKED`). All evidence logged in `findings.yaml` and `state.yaml`.

---

## 5. Capability Discovery & Realism

Capability audit rules:
- **`build`**: Wheel build & editable install (`.venv/bin/pip install -e . -e ./mcp`).
- **`lint`**: Marked `UNAVAILABLE` (no linter configured).
- **`typecheck`**: Marked `UNAVAILABLE` (no static type checker configured).
- **`combined_test_suite`**: Single combined test suite (`.venv/bin/pytest eval/`). Do NOT report identical pytest invocations as separate unit and integration suites.
- **`browser_verification`**: Browser workflow inspection via Chrome DevTools MCP tools (`navigate_page`, `take_snapshot`, `list_console_messages`, `list_network_requests`).
- **`automated_e2e_test`**: Marked `UNAVAILABLE` (no repeatable Playwright/Cypress suite exists). **Do NOT call browser verification automated E2E testing.**

---

## 6. Antigravity Compatibility Gate & Evidence-Based Readiness

Before declaring `SAFE TO WALK AWAY`, the controller MUST verify all 6 gate conditions:

1. **Skill Discovery**: Exact installed skills (`implement`, `tdd`, `code-review`, `diagnosing-bugs`, `validate-implementation-plan`, `autonomous-delivery`) are present and discoverable.
2. **Skill Reachability**: `implement` can explicitly reach `tdd` and `code-review`.
3. **Sub-agent Support**: `code-review`'s parallel `general-purpose` sub-agents are supported via `invoke_subagent` in Antigravity.
4. **Command Execution**: Required repository commands (`.venv/bin/pytest`, `git`, `gh`) execute cleanly without permission blocks.
5. **Browser Tools**: `chrome-devtools-mcp` tools are available for UI tasks.
6. **Worktree Isolation**: Pre-existing user changes recorded and isolated.

If any check fails or routine execution will prompt for ungranted permissions, emit `USER DECISION REQUIRED` or `BLOCKED_ENVIRONMENT` with exact evidence. Do NOT emit `SAFE TO WALK AWAY`.

If a Matt skill contains Claude-specific instructions that Antigravity cannot execute, transition immediately to `BLOCKED_ENVIRONMENT`. Do NOT silently imitate a successful invocation.

---

## 7. Dirty-Worktree Protection

1. Record baseline git commit (`git rev-parse HEAD`) and uncommitted user files (`git status --porcelain`).
2. Treat pre-existing uncommitted files as user-owned.
3. NEVER revert, overwrite, stage, or commit unrelated user changes.
4. If requested edits conflict with uncommitted user work, halt immediately and set terminal state to `BLOCKED_NEEDS_USER`.

---

## 8. Dry-Run Execution Mode (`--dry-run`)

When invoked with `--dry-run`:
1. Initialize run directory `.autonomous-delivery/runs/<run-id>/` with `dry_run: true`.
2. Perform request inspection, mode classification, and capability audit.
3. Generate `.autonomous-delivery/runs/<run-id>/plan.md`.
4. Run dry-run validation via `validate-implementation-plan`.
5. Perform Antigravity compatibility gate check.
6. Simulate skill routing trace step-by-step (showing which skill would be invoked at each stage).
7. Write complete state summary to `.autonomous-delivery/runs/<run-id>/state.yaml`.
8. Return without modifying source code, git commits, branches, issue tracker tickets, or external resources.

---

## 9. End-to-End Execution Flow

### Stage 1: Initialization & Compatibility Gate
- Create run directory `.autonomous-delivery/runs/<run-id>/` and set `.autonomous-delivery/active_run`.
- Record `baseline_revision` and `baseline_dirty_files`.
- Run Capability Audit and Antigravity Compatibility Gate.
- If gate passes cleanly, emit `SAFE TO WALK AWAY`. Otherwise emit `USER DECISION REQUIRED` or transition to `BLOCKED_ENVIRONMENT`.

### Stage 2: Planning & Validation
- Generate `.autonomous-delivery/runs/<run-id>/plan.md` and log decisions in `decisions.md`.
- Invoke `validate-implementation-plan`.
- Re-plan if `REVISE` (max 3 cycles). If limit reached, transition to `FAILED_TO_CONVERGE`.

### Stage 3: Implementation & Review Capture
- If `--dry-run` is active, trace skill routing and exit Stage 3 cleanly.
- If live run: Invoke `implement`. Capture review findings emitted by `implement`.

### Stage 4: Verification & Browser UI Testing
- Run available verification commands (`.venv/bin/pytest eval/`).
- For UI changes, launch app and verify workflows using Chrome DevTools MCP tools (`navigate_page`, `take_snapshot`, `list_console_messages`, `list_network_requests`).

### Stage 5: Code Review & Routing
- If findings or test failures exist, route:
  - **Clear defect**: `tdd` + repair.
  - **Unknown/intermittent/performance failure**: `diagnosing-bugs`.
  - **Plan flaw**: Return to Stage 2.
- Re-run `code-review` after repair iterations.

### Stage 6: Convergence & Integration
- Increment `repair_cycle_count` (max 6) and `no_progress_counter` (max 2).
- If limits exceeded, transition to `FAILED_TO_CONVERGE` with evidence in `findings.yaml`.
- Upon successful verification, update state to `COMPLETE` and present final walkthrough.
