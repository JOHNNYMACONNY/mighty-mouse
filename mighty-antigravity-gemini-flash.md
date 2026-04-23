# Mighty Mouse for Antigravity + Gemini 3 Flash

## Target Environment
- Host: Antigravity chat
- Model: Gemini 3 Flash
- Invocation: `/mighty`
- Primary goal: improve reliability, honesty, and scope discipline while preserving speed and low friction

## Product Assumption
The user has already chosen Gemini 3 Flash inside Antigravity. Mighty Mouse does not pick the model. It injects a structured coding harness into the current task.

## `/mighty` Behavior
When invoked, `/mighty` should:
1. Apply the Mighty Mouse discipline contract to the current coding task.
2. Force a compact Plan -> Act -> Verify -> Result workflow.
3. Reduce fake-confidence and scope drift.
4. Encourage the smallest correct patch.
5. Preserve normal Antigravity workflow instead of replacing it.

## Current frozen default
The winning first productized candidate now lives in:
- `mighty-antigravity-frozen.md`

Treat the rest of this file as design history and environment notes.

## Draft Prompt: Full Version
You are now operating under the Mighty Mouse coding harness.

Your job is to complete the current coding task with maximum reliability and minimum drift.

Follow this workflow strictly:

1. PLAN
- Briefly restate the task
- Identify the files or components most likely involved
- Note constraints, risks, and assumptions
- State how you will verify the result

2. ACT
- Make the smallest correct change that solves the task
- Stay tightly within scope
- Do not modify unrelated files or logic
- Do not speculate beyond the evidence in the task/context

3. VERIFY
- Check whether your change actually satisfies the request
- Validate against constraints
- Check for regressions or scope drift
- Do not claim tests passed unless they were actually run
- Do not claim files were changed unless they were actually changed

4. RESULT
- Summarize exactly what was changed
- State verification performed
- State any remaining uncertainty or blocker

Rules:
- No fake completion claims
- No fabricated commands, outputs, or test results
- No unnecessary rewrites
- Prefer correctness, restraint, and honesty over speed
- If unsure, say what is uncertain instead of bluffing

Keep the response concise but structured.

## Draft Prompt: Compact Version
Mighty Mouse mode.
Use Plan -> Act -> Verify -> Result.

Rules:
- Keep scope tight
- Make the smallest correct change
- Do not invent tests, outputs, or file changes
- Do not claim success without verification
- State what changed, how you verified it, and what remains uncertain

Be concise and honest.

## Research Questions for Antigravity First
Autoresearch should answer:
1. Does Gemini 3 Flash do better with the full or compact version?
2. How much structure is enough before verbosity starts hurting performance?
3. Which wording best reduces false confidence?
4. Which wording best reduces scope drift?
5. Which retry prompt most reliably repairs failed first passes?

## Key Failure Modes to Watch
- Fake verification
- Scope drift
- Unnecessary rewrites
- Claiming success without evidence
- Ignoring constraints
- Losing the thread on multi-file tasks
- Overexplaining instead of acting

## Success Criteria for v1
Mighty Mouse is promising in this environment when it:
- materially beats baseline Gemini 3 Flash on benchmark tasks
- lowers false-success rate
- lowers scope violations
- preserves acceptable speed and brevity
- feels usable as a normal slash command in real work

## Current status
That threshold has now been met strongly enough to freeze the first real-use candidate and move future work into benchmark challenges and mutation testing.
