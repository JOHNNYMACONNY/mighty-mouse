# Mighty Mouse Autoresearch Mutation Strategy

## Purpose
This file defines how `/autoresearch` should mutate Mighty Mouse variants between iterations.

The loop should not mutate prompts randomly. It should mutate based on measured failure patterns.

## Core Rule
Every mutation must be justified by evidence from the previous benchmark run.

Do not mutate because a variant sounds better.
Mutate because the scorecard and failure notes show a specific weakness.

## Allowed Mutation Axes

### 1. Prompt Length
Use when:
- output is too verbose
- tasks slow down too much
- structure is being ignored because prompt is overloaded

Mutation options:
- shorten rules
- compress repeated ideas
- reduce section wording
- remove low-value explanatory language

### 2. Verification Strictness
Use when:
- false-success rate is too high
- model claims tests passed without evidence
- verification compliance is weak

Mutation options:
- stronger honesty wording
- explicit prohibition on fabricated test claims
- clearer instruction to state verification limits
- require concrete evidence language in RESULT

### 3. Scope Control
Use when:
- scope violations are too frequent
- model edits unrelated files or logic
- model over-refactors

Mutation options:
- elevate scope rules higher in the prompt
- add "smallest correct change" emphasis
- explicitly forbid unrelated edits
- add "choose the narrower safe fix" language

### 4. Output Structure
Use when:
- model ignores sections
- responses become messy or inconsistent
- reasoning structure collapses on medium tasks

Mutation options:
- shorten section labels
- simplify to PLAN / ACT / VERIFY / RESULT only
- remove extra formatting complexity
- test bullet-based vs plain section format

### 5. Retry Language
Use when:
- first-pass success is low but repair potential exists
- retries restart from scratch too often
- retries break previously correct parts

Mutation options:
- tell retry to preserve working parts
- tell retry to repair only the failed portion
- require explanation of what changed from prior attempt
- discourage full rewrites unless necessary

### 6. Honesty Language
Use when:
- model sounds overconfident under ambiguity
- tasks with incomplete information are mishandled
- blocker honesty is poor

Mutation options:
- add stronger wording around uncertainty
- explicitly reward saying "I cannot verify this fully"
- reinforce assumption disclosure

## Mutation Triggers

### Trigger: High Scope Drift
If scope violation rate exceeds target:
- mutate scope control first
- do not lengthen every section blindly
- prefer sharper wording over more wording

### Trigger: High False-Success Rate
If false-success rate exceeds target:
- mutate verification strictness and honesty language first
- add direct no-fabrication language

### Trigger: Low First-Pass Success, Good Retry Recovery
If first-pass is weak but retry works:
- mutate planning clarity and scope wording
- preserve retry language that is already helping

### Trigger: Low Retry Recovery
If retries fail to improve outcomes:
- mutate retry language directly
- emphasize preserving working parts
- reduce restart-from-scratch behavior

### Trigger: High Verbosity / Friction
If output becomes too long or annoying:
- mutate toward shorter structure
- keep the highest-value rules only
- test compact variants before abandoning discipline

### Trigger: Weak Handling of Ambiguity
If honesty-trap tasks go badly:
- mutate honesty language
- require explicit assumptions
- require explicit uncertainty statements

## Mutation Limits
Per iteration, mutate only:
- one primary axis, or
- one primary axis plus one small supporting change

Do not change everything at once or the signal becomes muddy.

## Recommended Mutation Workflow
1. Run benchmark.
2. Review scorecard.
3. Identify top failure mode.
4. Choose one matching mutation axis.
5. Create one new variant from the current best prompt.
6. Re-run benchmark.
7. Compare against previous best.
8. Promote only if metrics improve meaningfully.

## Example Mutation Decisions

### Example 1
Problem:
- Variant A has good speed but high false-success

Mutation:
- keep compact structure
- strengthen verification honesty language only

### Example 2
Problem:
- Variant B has low drift but too much verbosity

Mutation:
- preserve section structure
- shorten wording inside each section

### Example 3
Problem:
- Variant C stays in scope but struggles on medium tasks

Mutation:
- keep scope-first rules
- add slightly clearer planning guidance

## Promotion Rule
A mutation wins only if it improves the scorecard without creating a worse tradeoff somewhere more important.

## Current Decision, Antigravity Wave 1
### Variant A vs Variant B
Current result:
- **Variant A** is the safer default base.
- **Variant B** has the stronger raw pass rate.
- **Variant B should not be promoted as-is.**

Why:
- Variant A scored worse on raw completion, but it stayed clean:
  - scope_violation_rate: 0.0
  - false_success_rate: 0.0
  - verification_compliance_rate: 1.0
- Variant B scored better on completion, but introduced the exact risks this harness is supposed to reduce:
  - scope_violation_rate: 0.4444
  - false_success_rate: 0.1111
  - scratch-file leakage on otherwise-simple tasks
  - weaker handling of exact requirement conflicts

Decision:
- Keep **Variant A** as the current default posture.
- Mutate **Variant B** instead of promoting it.
- Goal: keep Variant B's stronger task completion while restoring A-level discipline and trust.

### Next Mutation Target
Primary axis:
- **Scope Control**

Supporting axis:
- **Verification Strictness**

Reason:
- The biggest problem in Variant B is not lack of structure.
- The biggest problem is that it still permits small-but-real drift and one false-success style miss when the prompt requirement conflicts with inferred behavior.

### Mutation Requirements for the next Variant
The next Variant B mutation should explicitly add:
1. **No leftover scratch artifacts**
   - If temporary verification files are created, remove them before claiming done.
   - Prefer inline verification or existing test surfaces when possible.
2. **Requirement text outranks inferred intent**
   - If the prompt says `return "0.00" for None`, do not preserve an old symbol-prefixed behavior and call it success.
3. **Harder narrow-fix language**
   - Prefer the smallest fix that satisfies the literal task.
   - Avoid extra “helpful” behavior unless the task clearly asks for it.
4. **Explicit anti-overclaim check**
   - Before RESULT, verify that the claimed success matches the stated constraints and output contract, not just nearby code patterns.

### Current Decision, Antigravity Wave 2
### Variant B2 outcome
Current result:
- **Variant B2** is extremely capable on the clean fixture pack.
- **Variant B2 is still not promotable as-is.**

Why:
- pass_rate: 1.0
- first_pass_rate: 1.0
- verification_compliance_rate: 1.0
- but scope_violation_rate: 0.7778
- and false_success_rate: 0.1111

Interpretation:
- B2 solved almost everything cleanly at the code level.
- The remaining failure mode is now highly concentrated:
  - unnecessary verification artifacts like `test_helpers.py`
  - one cleanup overclaim when the response said the temp file was removed but the diff still showed it added

Decision:
- Do not promote B2.
- Preserve B2's structure and capability.
- Mutate specifically against verification-file creation and cleanup overclaiming.
- The next candidate should be **Variant B3**.

### Next Mutation Target After B2
Primary axis:
- **Scope Control** focused specifically on verification artifacts

Supporting axis:
- **Verification Strictness** focused specifically on cleanup claims

### Mutation Requirements for Variant B3
Variant B3 should explicitly add:
1. **No new verification files by default**
   - Prefer inspection, direct reasoning, or existing code paths first.
   - Treat new test files as a last resort, not a normal step.
2. **Artifact accounting in RESULT**
   - State whether any files were created.
   - State whether any temporary files were deleted.
3. **No cleanup claims without action**
   - Never say a file was removed unless it was actually removed.
4. **Limited verification is acceptable**
   - If no clean verification path exists, say verification is limited instead of creating junk.

### Current Decision, Antigravity Wave 3
### Variant B3 outcome
Current result:
- **Variant B3** is the strongest candidate so far.
- **Variant B3 should not be promoted yet without one more targeted pass.**

Why:
- pass_rate: 0.8889
- first_pass_rate: 0.8889
- scope_violation_rate: 0.1111
- false_success_rate: 0.1111
- verification_compliance_rate: 0.8889

Interpretation:
- B3 dramatically improved cleanliness versus B2.
- The remaining weakness is no longer artifact drift.
- The remaining weakness is occasional over-cleverness and fake confidence on simple tasks, especially when a direct built-in solution would have been safer.

Decision:
- Keep B3 as the current leading candidate.
- Do one more targeted mutation before expanding the benchmark.
- The next candidate should be **Variant B4**.

### Next Mutation Target After B3
Primary axis:
- **Verification Strictness** focused on runnable-as-written checks

Supporting axis:
- **Scope Control** focused on simple-first, no-clever-rewrite behavior

### Mutation Requirements for Variant B4
Variant B4 should explicitly add:
1. **Runnable-as-written check**
   - Before claiming success, check that the shown code would actually run.
   - Do not claim verification success for code that would fail due to missing imports or undefined names.
2. **Simple-first bias**
   - For tiny helper tasks, prefer the most direct idiomatic solution.
   - Avoid introducing regex, imports, or extra machinery when `split/join` or an equally simple built-in already solves it.
3. **Audit-only allowance**
   - If the current implementation already satisfies the task, say so plainly instead of rewriting for style.
4. **Import accounting**
   - If a new import is introduced, explicitly mention it in RESULT and confirm it is necessary.

## Long-Term Goal
Over time, `/autoresearch` should converge on:
- one default Mighty Mouse block
- one stricter fallback variant
- one repair-aware retry layer if needed

The end product should feel simple, but it should be backed by measured iteration.
