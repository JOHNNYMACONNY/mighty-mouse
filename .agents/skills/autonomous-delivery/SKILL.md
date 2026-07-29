---
name: autonomous-delivery
description: "Workspace-specific stateful controller for one-command software delivery with per-run state, dynamic capability discovery, task-dependent compatibility gates, and strict state-machine sequencing."
---

# Autonomous Delivery Controller

> **CRITICAL ENTRY GUARD**: If this skill is loaded directly without an active `/deliver` workflow run and initialized run state, do not inspect or edit application code. Stop and instruct the caller to invoke `/deliver`. Direct skill loading is not equivalent to workflow execution.

`autonomous-delivery` is the stateful controller governing automated software delivery in this repository. It operates from a natural-language request through per-run state creation, mode classification, task-dependent capability derivation, plan validation, evidence-based readiness emission, TDD implementation, verification, code review, targeted repair, and final integration.

---

## 1. Skill Integration & Dynamic Skill Path Resolution

This controller orchestrates the following installed skills by exact name without modifying, duplicating, or replacing them:

- `implement`: Feature and bug implementation skill. **Note**: `implement` already invokes `tdd` internally at pre-agreed seams and invokes `code-review` upon completion.
- `tdd`: Reference for red-green-refactor loop at public seams.
- `code-review`: Two-axis review (Standards & Spec) using parallel sub-agents against `baseline_revision`.
- `diagnosing-bugs`: Diagnosis loop for hard/intermittent bugs and performance regressions.
- `validate-implementation-plan`: Independent plan validator.

### Dynamic Skill Location
- During run initialization, locate the active installed `SKILL.md` file for each skill dynamically across user skills directories (`~/.gemini/config/skills/`, `.agents/skills/`).
- Record the resolved absolute path for each skill in `.autonomous-delivery/runs/<run-id>/state.yaml`. Never hardcode user-specific absolute paths in configuration files.

### Anti-Duplicate Orchestration Policy
- Because `implement` already invokes `tdd` and `code-review` internally, the controller MUST capture and interpret the review findings returned directly by `implement`.
- An explicit additional `code-review` call MUST be run ONLY:
  1. After repair iterations are applied,
  2. For final integration review before completion, or
  3. If the review inside `implement` failed or was skipped.
- Do NOT repeatedly run an unchanged `code-review` against an unchanged git diff.

---

## 2. Live Execution State Machine Sequencing

Every execution MUST strictly follow these 13 ordered stages:

```
[Stage A] Initialize run and protect existing work
   │
[Stage B] Inspect request and repository
   │
[Stage C] Select FAST, STANDARD, or DEEP
   │
[Stage D] Derive task-dependent required capabilities, skills, permissions & tools
   │
[Stage E] Generate plan & resolve routine reversible decisions autonomously
   │
[Stage F] Run validate-implementation-plan
   │
[Stage G] Handle validator result
   ├── READY ────────────────────────────────────────────────────────┐
   ├── REVISE ──> (increment planning_cycle_count, max 3) ──> [Stage E]│
   ├── BLOCKED (User decision / Irreversible action) ──> [BLOCKED_NEEDS_USER]
   └── BLOCKED (Missing environment / Tool) ───────────> [BLOCKED_ENVIRONMENT]
                                                                     │
[Stage H] Run compatibility & permission gates ONLY for plan-required capabilities <┘
   │
[Stage I] Emit SAFE TO WALK AWAY (ONLY after plan is READY & required gates pass)
   │
[Stage J] Implement (Invoke implement skill)
   │
[Stage K] Run deterministic verification & applicable browser verification
   │
[Stage L] Review, route findings, repair, and reverify
   │
[Stage M] Resolve terminal state (COMPLETE / BLOCKED_NEEDS_USER / BLOCKED_ENVIRONMENT / FAILED_TO_CONVERGE)
```

**CRITICAL RULE**: Never emit `SAFE TO WALK AWAY` before plan validation succeeds (`READY`) and all plan-required execution gates pass.

---

## 3. Task-Dependent Capability Requirements & Dynamic Discovery

Capabilities MUST be derived dynamically per request based on the validated plan. Do NOT require tools or permissions that the specific request does not need:

- **GitHub CLI (`gh`)**: Required ONLY if the request originated from an existing tracker item or authorized tracker work is explicitly required by mode policy.
- **Browser Tools (`chrome-devtools-mcp`)**: Required ONLY for UI/web workflow tasks (`browser_verification`). Do NOT require for non-UI tasks.
- **Build Command**: Required ONLY if the validated plan explicitly requires package compilation or wheel building. Do NOT require if a narrower test command is sufficient.

### Dynamic Capability Discovery
At run initialization, inspect current repository configuration to detect installed and configured tools dynamically:
- `build`: `.venv/bin/pip install -e . -e ./mcp` / `python -m build`
- `lint`: Inspect repository for `ruff`, `flake8`, `eslint`. Record `AVAILABLE` or `UNAVAILABLE`.
- `typecheck`: Inspect repository for `mypy`, `pyright`, `tsc`. Record `AVAILABLE` or `UNAVAILABLE`.
- `combined_test_suite`: Inspect for `.venv/bin/pytest`. Record `AVAILABLE` or `UNAVAILABLE`. Do NOT report identical pytest invocations as separate unit and integration suites.
- `browser_verification`: Inspect for `chrome-devtools-mcp` tools. Record `AVAILABLE` or `UNAVAILABLE`.
- `automated_e2e_test`: Inspect for Playwright/Cypress suites. Record `AVAILABLE` or `UNAVAILABLE`. Do NOT describe browser verification as automated E2E testing.

If a tool is configured later, discovery records `AVAILABLE` automatically on subsequent runs.

---

## 4. Per-Run Resumable State & Active-Run Pointer Rules

Every run creates a dedicated directory under `.autonomous-delivery/runs/<run-id>/`:

- `.autonomous-delivery/runs/<run-id>/state.yaml` - Structured state & resolved skill paths.
- `.autonomous-delivery/runs/<run-id>/plan.md` - Planning artifact.
- `.autonomous-delivery/runs/<run-id>/decisions.md` - Engineering decisions & assumptions log.
- `.autonomous-delivery/runs/<run-id>/findings.yaml` - Review findings & repair log.

### Conversation ID Mapping Rule
Every run MUST record a `conversationId`-to-`run-id` mapping file at `.autonomous-delivery/conversations/<conversation_id>.json` containing `{"run_id": "<run-id>"}` during Stage A. This mapping enables the PreToolUse safety hook (`delivery_guard.py`) to verify run authorization.

### Active-Run Pointer Rules
- An **implicit run** started without `--run-id` MAY write `.autonomous-delivery/active_run`.
- A run started with an **explicit `--run-id`** MUST NOT modify `.autonomous-delivery/active_run`.
- Concurrent or parallel runs REQUIRE explicit unique run IDs (`--run-id <run-id>`).

---

## 5. Mode Selection & Ticket Policy

- **FAST**: Localized change with existing test seam; no migrations, public APIs, or architectural changes. Ticket policy: NEVER create a tracker ticket unless request explicitly references an existing ticket (e.g. `#123`).
- **STANDARD**: Bounded feature or regression; UI behavior requiring browser verification. Ticket policy: Use internal run artifacts (`plan.md`, `decisions.md`) by default. Create tracker tickets ONLY if requested by user or originating from an existing ticket.
- **DEEP**: New subsystem, architecture refactoring, database migrations, or public API changes. Ticket policy: Tracker permitted if improving coordination. Keep decision work and implementation work separate. Never create tickets merely to document creating another ticket.

---

## 6. Code-Review Baseline & Diff Verification

1. Freeze `baseline_revision` (git SHA via `git rev-parse HEAD`) during initialization (Stage A).
2. When running `code-review`, compare `HEAD` against that exact `baseline_revision` SHA (e.g. `git diff <baseline_revision>...HEAD`), NOT the symbolic ref `HEAD`.
3. Verify that the reviewed diff contains the intended implementation changes.
4. If `implement` leaves uncommitted changes that the installed `code-review` skill cannot inspect, do NOT claim successful review. Resolve the uncommitted changes or return `BLOCKED_ENVIRONMENT`.

---

## 7. Normalized Validator Routing & Repair Convergence

### Validator Routing Rules
- **`READY`**: Proceed directly to Stage H (Required Compatibility & Permission Gates).
- **`REVISE`**: Increment `planning_cycle_count`. Revise plan (max 3 cycles). If cycle 3 fails validation, transition state to `FAILED_TO_CONVERGE`.
- **`BLOCKED`**: Does **NEVER** increment `planning_cycle_count`. Maps immediately based on evidence:
  - User decision / irreversible action needed -> `BLOCKED_NEEDS_USER`
  - Missing environment / missing required tool -> `BLOCKED_ENVIRONMENT`

### False-Positive Review Finding Closure
A code-review finding may be closed without code changes ONLY when `.autonomous-delivery/runs/<run-id>/findings.yaml` records:
- `finding_id`: Unique identifier
- `counter_evidence`: Explicit technical justification
- `verification_command_or_source`: Exact command or repo file proving false positive
- `disposition`: `FALSE_POSITIVE`

### Concrete No-Progress Definition
A repair cycle counts as **no progress** when ALL of the following remain unchanged from the previous cycle:
1. Failing test set
2. Unresolved finding IDs and severities
3. Relevant git diff
4. Bug reproduction result

Two consecutive no-progress cycles (or 6 total repair cycles) map directly to `FAILED_TO_CONVERGE`.

---

## 8. Normalized Completion Criteria

`COMPLETE` requires ALL of the following:
- Explicit acceptance criteria satisfied.
- Required deterministic test checks passing (`combined_test_suite`).
- Required UI/browser verification checks passing (`browser_verification`, if UI task).
- Zero unresolved actionable spec findings.
- Zero unresolved critical or major standards findings.
- Intended git diff reviewed against frozen `baseline_revision`.
- Applicable authorized tracker work updated.

---

## 9. Dry-Run Execution Mode (`--dry-run`)

When invoked with `--dry-run`:
1. Initialize run directory `.autonomous-delivery/runs/<run-id>/` with `dry_run: true`.
2. Inspect request, classify mode, and audit required capabilities dynamically.
3. Generate `.autonomous-delivery/runs/<run-id>/plan.md`.
4. Run validation via `validate-implementation-plan`.
5. If valid, evaluate required compatibility gates.
6. Simulate skill routing trace step-by-step.
7. Save state to `state.yaml` with terminal status `DRY_RUN_COMPLETE` (requiring unchanged `HEAD` and unchanged working-tree status relative to run initialization) and return without modifying source code, git state, or external resources.

---

## 10. Safety Guardrails

- **NEVER** silently deploy to production or external environments.
- **NEVER** push commits directly to protected branches or force-push.
- **NEVER** delete production databases, tables, or uncommitted user files.
- **NEVER** bypass failing tests or suppress errors without root-cause resolution.
