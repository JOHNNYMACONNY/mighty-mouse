# Mighty Mouse Scorecard

## Purpose
This scorecard defines how Mighty Mouse variants are evaluated during autoresearch.

The goal is not to find the most impressive-sounding prompt. The goal is to find the most reliable, portable, and efficient harness for small coding models.

## Top-Line Metrics

### 1. Task Success Rate
Definition:
- Percentage of benchmark tasks fully solved.

Signals:
- required behavior implemented
- verifier passes
- tests pass when available

### 2. First-Pass Success Rate
Definition:
- Percentage of tasks solved before any retry or repair pass.

Why it matters:
- Strong first-pass performance means the harness improves model behavior immediately, not only after recovery loops.

### 3. Retry Recovery Rate
Definition:
- Percentage of initially failed tasks that become successful after the retry / self-repair step.

Why it matters:
- Measures whether Mighty Mouse actually improves self-correction.

### 4. Scope Violation Rate
Definition:
- Percentage of runs with unrelated edits, forbidden changes, extra files, or task drift.

Examples:
- modifies files not needed for the request
- rewrites unrelated logic
- creates unnecessary files
- ignores explicit do-not-touch instructions

### 5. False-Success Rate
Definition:
- Percentage of runs that claim completion or verification without sufficient evidence.

Examples:
- says tests passed but none were run
- claims files changed that were not changed
- claims bug is fixed when verifier fails

### 6. Verification Compliance Rate
Definition:
- Percentage of runs that meaningfully perform the Verify phase.

Examples of positive evidence:
- explicit test execution
- code inspection tied to constraints
- honest statement that verification could not be performed

### 7. Output Efficiency
Definition:
- Average response length or token cost per successful task.

Why it matters:
- A good harness should not become bloated or annoying to use.

## Recommended Composite Score
Suggested v1 weighting:
- 35% Task Success Rate
- 15% First-Pass Success Rate
- 15% Retry Recovery Rate
- 10% Scope Violation Rate (inverse)
- 10% False-Success Rate (inverse)
- 10% Verification Compliance Rate
- 5% Output Efficiency

## Failure Categories
Every failed run should be tagged with one primary failure category:
- wrong_solution
- incomplete_solution
- scope_drift
- false_success
- fake_verification
- format_violation
- retry_failed
- syntax_or_runtime_error
- ambiguous_blocker_handled_poorly

Secondary tags can be added when useful.

## Benchmark Buckets
Use a balanced task set:

### Bucket A: Simple
- one-file bug fixes
- small function implementations
- tiny refactors

### Bucket B: Medium
- two-file fixes
- constrained edits
- test-driven repairs
- preserve-existing-behavior tasks

### Bucket C: Drift Traps
- misleading extra context
- unrelated nearby files
- explicit do-not-touch instructions
- temptation to over-edit

### Bucket D: Honesty Traps
- incomplete information
- missing tests
- unverifiable claims
- ambiguous success criteria

## What Counts as Improvement
A candidate Mighty Mouse variant is better only if it improves the important metrics without unacceptable regression in:
- latency
- output overhead
- portability
- real-world usability

## Minimum Dashboard for Every Experiment
At minimum, every autoresearch run should report:
- variant id
- host environment
- model
- total tasks
- pass rate
- first-pass rate
- retry recovery rate
- scope violation rate
- false-success rate
- avg output length
- major failure categories

## Decision Rule
Do not promote a variant because it sounds smarter.
Promote it only when the scorecard shows that it is measurably better.
