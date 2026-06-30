# Real-Project Validation Study Plan

Status: **prospective protocol frozen before Task MM-001**

This study evaluates whether activating Mighty Mouse improves real coding-task
outcomes. It does not treat synthetic benchmarks, reconstructed runs, or work
completed before this protocol was frozen as real-project evidence.

## Experimental unit

Each task is one paired comparison from a single recorded Git commit:

- **Control:** the coding agent receives the fixed task brief and works normally.
- **Harness:** the same agent and model receive the same task brief with Mighty
  Mouse activated at the task's recorded complexity level.

Both conditions must use isolated worktrees created from the same base commit.
They must use the same dependency versions, environment variables, timeout,
network policy, and acceptance commands. Neither condition may inspect the
other condition's transcript, diff, or verifier output before it finishes.

## Procedure

1. Confirm the source repository is clean and record its base commit.
2. Freeze the task brief, allowed paths, acceptance commands, agent, model,
   model settings, dependency snapshot, and timeout.
3. Create control and harness worktrees from the recorded base commit.
4. Run the control condition and preserve its raw transcript, timestamps, diff,
   command output, and final commit.
5. Run the harness condition independently and preserve the same artifacts.
   Mighty Mouse may perform at most three verify-fix rounds.
6. Run the fixed acceptance commands in a fresh process for each condition.
7. Review both diffs without using the condition labels where practical.
8. Record both conditions with `eval/record_real_project_trial.py`.
9. Select the implementation to merge based on correctness first, then scope,
   maintainability, and simplicity. The selected condition is not necessarily
   the harness condition.
10. Retain failed, tied, slower, and unfavorable Mighty Mouse results.

If either condition sees the other's implementation, starts from a different
commit, or receives materially different requirements, mark the pair invalid
and repeat it from a new base commit. Do not repair or reconstruct the record.

## Measurement rules

- **First-try pass:** all fixed acceptance commands pass before any feedback-led
  repair. A self-initiated edit before the first acceptance run is still part of
  the first attempt.
- **Retry rounds:** the number of acceptance-result-driven repair cycles.
- **Scope violations:** changed paths outside the frozen allowed-path set. Every
  path is retained, even if reverted later.
- **Duration:** monotonic wall-clock seconds from task delivery until the final
  acceptance result, including retries but excluding environment provisioning.
- **Quality score:** blind reviewer score from 1 to 5 using the rubric below.

### Quality rubric

| Score | Meaning |
|---:|---|
| 1 | Incorrect, unsafe, or not maintainable despite any passing narrow checks |
| 2 | Partially correct with important defects or unnecessary scope |
| 3 | Correct and acceptable, with ordinary maintainability or clarity issues |
| 4 | Correct, focused, well-tested, and easy to maintain |
| 5 | Exceptional solution with unusually strong design and regression coverage |

A passing test suite is evidence for tested behavior, not an automatic quality
score. The reviewer records a short rationale before condition labels are
revealed.

## Planned task corpus

The order is fixed. A later task may start from code selected after an earlier
pair, but both conditions within that later task must still share one base
commit. If a task stops being genuine before it starts, replace it prospectively
and document the reason; do not substitute a completed task.

### MM-001 — Add a public `verify` CLI command

Repository: `mighty-mouse`

Task brief: Add `mighty-mouse verify <workspace>` as a thin interface to the
generic verifier. Support explicit test, lint, and build command overrides,
repeatable allowed paths, timeout configuration, readable human output, and
truthful exit codes: `0` when all applicable checks pass, `1` when verification
runs and fails, and `2` for invalid CLI input or an unusable workspace.

Acceptance gates:

- CLI tests cover passing, failing, invalid-workspace, override, scope, and
  timeout behavior without relying on external network services.
- Existing `doctor`, `demo`, and `benchmark` behavior remains green.
- `pytest -q` passes.
- Installed-wheel smoke tests prove the command is not source-tree-dependent.

### MM-002 — Add stable JSON output

Repository: `mighty-mouse`

Task brief: Add `--json` output to the public `verify` and protocol interfaces.
Define and document a versioned schema while preserving existing human-readable
output and exit-code behavior.

Acceptance gates:

- JSON is valid on success and failure and contains no human prose on stdout.
- The schema version and required fields have regression tests.
- Human output remains backward-compatible.
- `pytest -q` and installed-wheel smoke tests pass.

### MM-003 — Add release-grade continuous integration

Repository: `mighty-mouse`

Task brief: Add GitHub Actions that test supported Python 3.10 through 3.13,
build both core and MCP wheels, install those wheels into a clean environment,
and smoke-test the CLI and MCP imports.

Acceptance gates:

- Workflow YAML parses and uses only pinned major versions of trusted actions.
- The matrix runs the complete relevant suite, not a reduced placeholder suite.
- Wheel installation tests avoid importing from the checkout accidentally.
- Local equivalents of all feasible workflow commands pass.

### MM-004 — Verify mixed Python and Node repositories

Repository: `mighty-mouse`

Task brief: Make auto-detection truthful for a repository containing both Python
and Node project markers. Run applicable checks for both ecosystems, expose the
detection decision in structured results, and document override behavior.

Acceptance gates:

- Fixtures cover Python-only, Node-only, mixed, and partially configured repos.
- A failure in either detected ecosystem fails the combined verification.
- Missing optional tools produce explicit skipped/warning results, not false
  success or an unhandled exception.
- `pytest -q` passes.

### PORT-001 — Remove generated repository debris

Repository: portfolio (`AudioServiceApp`)

Task brief: Identify tracked build, test, cache, and local-environment artifacts;
remove only reproducible debris; and strengthen ignore rules without hiding
source files, fixtures, or intentional evidence.

Acceptance gates:

- A before/after inventory explains every removed or newly ignored path.
- The application build and test commands pass.
- A fresh build does not dirty Git with generated debris.
- No required deployment or content artifact is removed.

### PORT-002 — Validate Work-page destinations

Repository: portfolio (`AudioServiceApp`)

Task brief: Add automated validation for Work-page project routes, slugs, primary
CTAs, repository URLs, and external destinations using the site's actual content
source rather than a duplicated test-only list.

Acceptance gates:

- Tests fail for broken internal routes, malformed URLs, duplicate slugs, and
  missing primary CTAs.
- External checks are deterministic and do not require live network access.
- Existing build and test commands pass.

### PORT-003 — Publish the evidence-correct Mighty Mouse case study

Repository: portfolio (`AudioServiceApp`)

Task brief: Update the Mighty Mouse case study to explain the real problem,
generic verifier, agent integrations, and evidence in plain language. State that
the frozen bare and harness conditions both passed 15/15 tasks; retain the
historical 29.5% latency result only with its correct 15-paired-task scope; and
provide working repository and contact CTAs.

Acceptance gates:

- Every quantitative claim maps to a frozen Mighty Mouse evidence artifact.
- No success-rate improvement is claimed from the ceiling-effect corpus.
- Content tests, link validation, application tests, and production build pass.
- A rendered desktop and mobile review finds no clipping or ambiguous CTA.

### AUDIO-001 — Add a SoundCloud upload dry run

Repository: audio-to-website pipeline

Task brief: Extend the existing new-export pipeline with an optional SoundCloud
destination that defaults to dry-run behavior. A dry run must show the selected
audio file, normalized metadata, intended destination, and validation errors
without uploading or mutating remote state.

Acceptance gates:

- API behavior is mocked in automated tests; tests never publish media.
- Duplicate exports, missing credentials, invalid metadata, and unsupported
  audio files are handled explicitly.
- Live publishing requires a separate affirmative flag or configuration value.
- Existing website-upload behavior remains green.

### SOCIAL-001 — Add a carousel selection preview

Repository: Instagram carousel automation

Task brief: Add a dry-run preview report that shows the proposed assets, their
source folders, selection balance, prior-post status, and ordering before any
Meta Business Suite draft is created.

Acceptance gates:

- Preview mode creates no browser draft and performs no remote mutation.
- Tests prove no duplicate selection and the defined cross-folder balancing
  behavior over deterministic fixtures.
- Insufficient inventory and corrupt history state produce actionable errors.
- The report is useful both in a terminal and as a saved artifact.

### VIDEO-001 — Harden synchronization edge cases

Repository: automated video editor

Task brief: Handle clips with mismatched frame rates and clips with missing or
unusable audio. Preserve synchronization when conversion is possible and fail
early with actionable diagnostics when it is not.

Acceptance gates:

- Small deterministic media fixtures cover mismatched frame rates, missing
  audio, silent audio, and a valid two-source event.
- Output duration and synchronization tolerance are asserted numerically.
- Failures do not leave misleading partial output files.
- The existing face-cam overlay workflow remains green.

## Reporting gate

The study is complete only after at least ten valid pairs are recorded. The
report must show per-task results and aggregate first-try passes, retries, scope
violations, duration, and quality. It must discuss negative and inconclusive
results. A generalized improvement claim is allowed only if the recorded data
actually demonstrates one; otherwise the result is reported as no demonstrated
improvement.
