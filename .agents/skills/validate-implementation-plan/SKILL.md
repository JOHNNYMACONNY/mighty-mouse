---
name: validate-implementation-plan
description: "Independently evaluate a proposed implementation plan for completeness, testability, capability verification, and repository alignment. Returns READY, REVISE, or BLOCKED."
---

# Validate Implementation Plan

This skill provides an independent, objective evaluation of a proposed implementation plan before code edits begin. It verifies that the plan is realistic, testable, fully covers the user's request, and aligns with repository conventions without relying on subjective confidence claims or percentage scores.

## Evaluation Inputs

1. **User Request & Requirements**: The original natural-language instruction and acceptance expectations.
2. **Proposed Implementation Plan**: The run-specific planning artifact (`.autonomous-delivery/runs/<run-id>/plan.md`).
3. **Repository Context & Capabilities**: Codebase structure, `CONTEXT.md`, `AGENTS.md`, dirty-worktree state, and verified capabilities (`build`, `lint`, `typecheck`, `combined_test_suite`, `browser_verification`, `automated_e2e_test`).

## Capability Audit Guidelines

Do NOT confuse test runners with linters, typecheckers, or automated E2E suites:
- **`build`**: Compiling, wheel building, editable install (`.venv/bin/pip install -e . -e ./mcp`, `python -m build`).
- **`lint`**: Code style/linter tools (`ruff`, `flake8`, `eslint`). If unconfigured in repository, mark `UNAVAILABLE`.
- **`typecheck`**: Static type checkers (`mypy`, `pyright`, `tsc`). If unconfigured in repository, mark `UNAVAILABLE`.
- **`combined_test_suite`**: Single combined test suite (`.venv/bin/pytest eval/`). Do NOT report identical pytest invocations as separate unit and integration suites unless distinct markers or directories exist.
- **`browser_verification`**: Interactive browser UI/workflow inspection using Chrome DevTools MCP tools (`navigate_page`, `take_snapshot`, `list_console_messages`, `list_network_requests`).
- **`automated_e2e_test`**: Repeatable automated E2E testing framework (Playwright, Cypress, Selenium). If unconfigured in repository, mark `UNAVAILABLE`. **Do NOT describe browser verification as automated E2E testing.**

Never invent substitute commands or claim unverified tools provide equivalent coverage.

## Evaluation Criteria

An implementation plan must be evaluated along six mandatory dimensions:

1. **Requirement Coverage**: Every explicit requirement and implicit edge case in the request is addressed by a specific change in the plan.
2. **File & Seam Verification**: All referenced existing files, modules, and interfaces exist at declared paths. New file paths and public seams are explicitly specified.
3. **Capability & Environment Verification**: Commands for available capabilities (`build`, `combined_test_suite`, `browser_verification`) are verified. Missing capabilities (`lint`, `typecheck`, `automated_e2e_test`) are noted as `UNAVAILABLE` rather than assumed.
4. **Testability & Seam Definition**: Clear, pre-agreed public seams and deterministic test commands are explicitly defined.
5. **Assumption & Decision Completeness**: No critical ambiguous assumptions remain unresolved. Reversible engineering choices adopt established repository conventions.
6. **Risk, Regression & Isolation Coverage**: Potential side-effects and pre-existing user work (`git status`) have explicit isolation and verification coverage.

## Decision Rules

The skill MUST return exactly ONE of the following decision codes:

### 1. READY
Returned ONLY when ALL of the following are true:
- Every requirement is fully covered with explicit implementation steps.
- All existing referenced files and components are verified to exist on disk.
- Necessary tools, execution commands, and permissions are verified available.
- Acceptance checks and test commands are explicitly defined.
- Pre-existing user work is isolated and protected.
- No unresolved critical assumptions remain.

### 2. REVISE
Returned when the plan has fixable gaps that can be resolved autonomously through further codebase inspection or plan refinement without asking the user:
- Missing file paths or inaccurate seam definitions.
- Vague test commands or incomplete edge-case coverage.
- Omitted minor requirements clear from repository context.
- Unspecified implementation details for reversible choices.

### 3. BLOCKED
Returned ONLY when the plan cannot proceed without direct user intervention:
- Contradictory or mutually exclusive product requirements (e.g. demanding 100% backward compatibility while deleting the API).
- Missing credentials, tokens, or external service permissions.
- Required external dependencies or environments that cannot be installed or accessed locally.
- Irreversible operations (data destruction, dropping tables, overwriting uncommitted user work) requiring explicit user consent.

## Output Schema

The skill must format its output as follows:

```markdown
## Validation Result: [READY | REVISE | BLOCKED]

### Summary
[Concise summary of the evaluation decision]

### Audit Checklist
- [x/ ] Requirement Coverage: [Details]
- [x/ ] File & Seam Verification: [Details]
- [x/ ] Capabilities & Environment: [Details]
- [x/ ] Testability & Acceptance: [Details]
- [x/ ] Isolation & Worktree Safety: [Details]
- [x/ ] Assumptions & Conventions: [Details]

### Actionable Feedback (Required for REVISE / BLOCKED)
1. [Specific plan modification or missing prerequisite required]
```
