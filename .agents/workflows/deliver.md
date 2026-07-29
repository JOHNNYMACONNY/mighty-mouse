---
description: Run autonomous software delivery through planning, validation, implementation, testing, review, repair, and final verification.
---

# Autonomous Delivery Workflow (/deliver)

Run workspace-specific autonomous software delivery from natural-language request through per-run planning, implementation, verification, code review, repair, and final integration.

## Usage

```bash
/deliver [--dry-run] [--run-id <run-id>] <request description>
```

## Workflow Execution State Machine

Execution MUST strictly follow these 13 ordered stages:

### Stage A: Initialize Run & Protect Existing Work
- Read request and check for `--dry-run` and `--run-id` flags.
- Generate unique `<run-id>` if omitted (e.g. `run-20260728-214800`).
- Create run directory at `.autonomous-delivery/runs/<run-id>/`.
- **Conversation ID Mapping Rule**: Record `conversationId`-to-`run-id` mapping in `.autonomous-delivery/conversations/<conversation_id>.json` containing `{"run_id": "<run-id>"}` so the PreToolUse hook (`delivery_guard.py`) can authorize operations for this session.
- **Active-Run Pointer Rule**: Write `.autonomous-delivery/active_run` ONLY if running implicitly without `--run-id`. If started with explicit `--run-id`, do NOT modify `.autonomous-delivery/active_run`.
- Record `baseline_revision` (`git rev-parse HEAD`) and uncommitted user files (`git status --porcelain`) in `.autonomous-delivery/runs/<run-id>/state.yaml`. Uncommitted user files are marked user-owned and protected.

### Stage B: Inspect Request & Repository
- Inspect request text, `CONTEXT.md`, `AGENTS.md`, and codebase structure.

### Stage C: Select Mode
- Automatically classify request into `FAST`, `STANDARD`, or `DEEP`. Log classification rationale.

### Stage D: Derive Required Capabilities, Skills, Permissions & Tools
- Dynamically discover repository capabilities: `build`, `lint`, `typecheck`, `combined_test_suite`, `browser_verification`, `automated_e2e_test`.
- Derive capabilities required specifically by this request:
  - `gh` CLI required ONLY if task references an existing ticket or authorized tracker work is required.
  - Browser tools (`chrome-devtools-mcp`) required ONLY for UI tasks.
  - Build command required ONLY if package build is explicitly required by plan.
- Dynamically locate active installed `SKILL.md` paths for `implement`, `tdd`, `code-review`, `diagnosing-bugs`, and `validate-implementation-plan`, and record resolved paths in `state.yaml`.

### Stage E: Generate Plan & Resolve Reversible Decisions
- Generate `.autonomous-delivery/runs/<run-id>/plan.md`.
- Resolve routine reversible engineering choices autonomously following repository conventions, and log them in `decisions.md`.

### Stage F: Run Plan Validation
- Invoke `validate-implementation-plan` on `.autonomous-delivery/runs/<run-id>/plan.md`.

### Stage G: Handle Validator Result
- **`READY`**: Continue to Stage H.
- **`REVISE`**: Increment `planning_cycle_count`. If `planning_cycle_count` <= 3, return to Stage E. If cycle 3 fails, transition state to `FAILED_TO_CONVERGE` immediately.
- **`BLOCKED` (User Decision / Irreversible Action)**: Transition state to `BLOCKED_NEEDS_USER` immediately. Do NOT increment `planning_cycle_count`.
- **`BLOCKED` (Missing Environment / Required Tool)**: Transition state to `BLOCKED_ENVIRONMENT` immediately. Do NOT increment `planning_cycle_count`.

### Stage H: Run Compatibility & Permission Gates
- Execute compatibility and permission checks ONLY for capabilities derived in Stage D for this specific plan.
- Verify subagent reachability (`invoke_subagent`), skill reachability, required tool availability, and execution permissions.

### Stage I: Emit Readiness Status
- Emit `SAFE TO WALK AWAY` **ONLY** after plan validation succeeded (`READY`) AND all plan-required execution gates pass cleanly in Stage H.
- If gates fail or routine operations require ungranted permissions, emit `USER DECISION REQUIRED` or transition to `BLOCKED_ENVIRONMENT`. **Never emit `SAFE TO WALK AWAY` before plan validation succeeds.**

### Stage J: Implement
- **If `--dry-run` is active**: Simulate skill routing trace and skip code modification.
- **If live run**: Invoke `implement` skill. Capture review findings emitted by `implement`.

### Stage K: Run Verification
- Execute deterministic test checks (`combined_test_suite`: `.venv/bin/pytest eval/`).
- For UI tasks, launch application and execute browser workflow verification using Chrome DevTools MCP tools (`navigate_page`, `take_snapshot`, `list_console_messages`, `list_network_requests`).

### Stage L: Review, Route Findings, Repair & Reverify
- Invoke `code-review` against frozen `baseline_revision` SHA (`git diff <baseline_revision>...HEAD`).
- Evaluate `Standards` and `Spec` finding axes.
- Route findings:
  - Clear defect -> `tdd` + repair.
  - Intermittent/resistant failure -> `diagnosing-bugs`.
  - False positive -> Close finding ONLY if counter-evidence, verification command, and disposition `FALSE_POSITIVE` are recorded in `findings.yaml`.
- Re-run `code-review` after repair iterations.
- Track repair cycles: Increment `repair_cycle_count` (max 6). Increment `no_progress_counter` if test set, findings, diff, and repro result remain unchanged (max 2 consecutive). If limits exceeded, transition to `FAILED_TO_CONVERGE`.

### Stage M: Resolve Terminal State
Execution halts when `state.yaml` reaches one of five normalized terminal statuses:

- **`COMPLETE`**: Acceptance criteria satisfied, required tests pass, required browser verification passes, zero unresolved critical/major findings, diff reviewed against `baseline_revision`, tickets updated.
- **`DRY_RUN_COMPLETE`**: Dry-run simulation completed. Requires unchanged `HEAD` and unchanged working-tree status (`git status --porcelain`) relative to run initialization.
- **`BLOCKED_NEEDS_USER`**: True blocker requires explicit user intervention, permissions, or product decision.
- **`BLOCKED_ENVIRONMENT`**: Required system dependency missing or compatibility gate failure.
- **`FAILED_TO_CONVERGE`**: Exhausted 3 planning cycles, 6 repair cycles, or 2 consecutive no-progress cycles. Evidence logged in `findings.yaml`.

## Final Report
Present terminal status, summary of run artifacts (`.autonomous-delivery/runs/<run-id>/`), and verification evidence to the user.
