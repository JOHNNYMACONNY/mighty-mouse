# Autonomous Delivery Workflow (/deliver)

Run workspace-specific autonomous software delivery from natural-language request through per-run planning, implementation, verification, code review, repair, and final integration.

## Usage

```bash
/deliver [--dry-run] [--run-id <run-id>] <request description>
```

## Workflow Execution Steps

### 1. Initialize Per-Run Context
- Read request and check for `--dry-run` and `--run-id` flags.
- Generate unique `<run-id>` if not supplied (e.g. `run-20260728-214200`).
- Create run directory at `.autonomous-delivery/runs/<run-id>/`.
- Update active run pointer file at `.autonomous-delivery/active_run`.
- Record baseline revision (`git rev-parse HEAD`) and uncommitted user files (`git status --porcelain`) in `.autonomous-delivery/runs/<run-id>/state.yaml`.

### 2. Antigravity Compatibility & Capability Gate
- Audit repository capabilities separately:
  - `build`: `.venv/bin/pip install -e . -e ./mcp` (Available)
  - `lint`: Unavailable
  - `typecheck`: Unavailable
  - `combined_test_suite`: `.venv/bin/pytest eval/` (Available)
  - `browser_verification`: `chrome-devtools-mcp` (Available)
  - `automated_e2e_test`: Unavailable
- Run Antigravity Compatibility Gate:
  - Discover exact installed skills (`implement`, `tdd`, `code-review`, `diagnosing-bugs`, `validate-implementation-plan`, `autonomous-delivery`).
  - Verify subagent reachability (`invoke_subagent`).
  - Verify browser tool availability (`chrome-devtools-mcp`).
  - Verify permissions for command execution.
- Status Emission:
  - Emit `SAFE TO WALK AWAY` ONLY if all gate checks pass and no ungranted permission prompts will occur.
  - Otherwise emit `USER DECISION REQUIRED` or transition state to `BLOCKED_ENVIRONMENT`.

### 3. Mode Classification & Ticket Policy
- Classify request into `FAST`, `STANDARD`, or `DEEP`.
- Enforce ticket policy:
  - **FAST**: No tracker tickets unless request references an existing ticket.
  - **STANDARD**: Internal run artifacts (`plan.md`, `decisions.md`) by default.
  - **DEEP**: Separate decision work and implementation work if tracker is used.

### 4. Planning & Validation
- Generate `.autonomous-delivery/runs/<run-id>/plan.md` and `decisions.md`.
- Invoke `validate-implementation-plan`.
- Re-plan if `REVISE` (max 3 cycles). If limit reached, transition state to `FAILED_TO_CONVERGE`.

### 5. Execution, Verification & Repair Loop
- **If `--dry-run` is active**:
  - Perform read-only skill routing trace showing which skill is invoked at each stage.
  - Save dry-run state to `state.yaml`.
  - Exit without modifying source code, git commits, or tickets.
- **If live run**:
  - Invoke `implement` (which invokes `tdd` and `code-review` internally).
  - Run deterministic test suite (`.venv/bin/pytest eval/`).
  - For UI changes, launch app and verify workflows with Chrome DevTools MCP tools (`navigate_page`, `take_snapshot`, `list_console_messages`, `list_network_requests`).
  - Capture review findings. Route defects to `tdd` or `diagnosing-bugs`.
  - Re-run `code-review` after repairs. Max 6 repair cycles or 2 no-progress cycles before transitioning to `FAILED_TO_CONVERGE`.

### 6. Terminal State Resolution
Execution stops when state in `.autonomous-delivery/runs/<run-id>/state.yaml` reaches one of the normalized terminal statuses:

- **`COMPLETE`**: All acceptance criteria met, tests pass, zero critical review findings.
- **`BLOCKED_NEEDS_USER`**: True blocker requires explicit user intervention or permissions.
- **`BLOCKED_ENVIRONMENT`**: System dependency missing or Antigravity compatibility gate failure.
- **`FAILED_TO_CONVERGE`**: Exhausted repair cycles (6), no-progress cycles (2), or planning cycles (3). Evidence logged in `findings.yaml`.

### 7. Final Report
Present terminal status, summary of run artifacts (`.autonomous-delivery/runs/<run-id>/`), and verification evidence to the user.
