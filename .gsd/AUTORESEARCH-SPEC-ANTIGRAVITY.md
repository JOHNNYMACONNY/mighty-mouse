# Autoresearch Specification: Mighty Mouse in Antigravity

## Purpose
This spec defines the primary research loop for Mighty Mouse as an in-agent slash-command harness.

The research goal is not to optimize an API wrapper. The goal is to optimize Mighty Mouse so that it improves coding reliability when the user is already inside Antigravity and has already selected a small model, starting with Gemini 3 Flash.

## Target Environment
- Host: Antigravity chat
- Model: user-selected model in the current chat
- Primary initial target: Gemini 3 Flash
- Invocation pattern:
  - user selects Gemini 3 Flash in Antigravity
  - user invokes `/autoresearch`
  - `/autoresearch` evaluates and improves Mighty Mouse variants for that same environment

## Core Research Question
How much does Mighty Mouse improve coding reliability, scope discipline, and verification honesty for Gemini 3 Flash inside Antigravity chat?

## Optimization Target
Optimize the Mighty Mouse slash-command contract, not the underlying model.

Primary optimization surfaces:
- `/mighty` prompt wording
- response structure requirements
- verification wording
- retry wording
- scope-discipline wording
- compact vs detailed harness variants
- Antigravity-specific wrapper behavior

## Product Assumption
The model is chosen before Mighty Mouse is invoked.
Mighty Mouse does not choose the model, call an API, or replace the host agent.
It acts as a discipline layer inside the current Antigravity session.

## Research Modes

### 1. Field Mode (Primary)
Use the actual Antigravity environment with the actual selected model.

Purpose:
- optimize real-world performance
- measure practical usefulness
- tune slash-command behavior as actually experienced by users

Tradeoffs:
- less deterministic than direct API testing
- influenced by host behavior, session context, and model/provider drift

### 2. Lab Mode (Optional Secondary)
Use local or API-driven reproductions only when tighter control is needed.

Purpose:
- isolate specific prompt effects
- debug eval harness behavior
- compare variants under more repeatable conditions

Rule:
Lab mode supports research, but Field Mode is the source of truth for Mighty Mouse product decisions.

## Evaluation Metrics
For each candidate variant, measure:

### Primary
- Task Success Rate
- First-Pass Success Rate
- Retry Recovery Rate
- Scope Violation Rate
- False-Success Rate

### Secondary
- Verification Compliance Rate
- Average Output Length
- Average Turn Count
- Latency / Friction
- Subjective usability in real chat workflow

## Failure Categories
Every failed run should be tagged with one primary failure mode:
- wrong_solution
- incomplete_solution
- scope_drift
- false_success
- fake_verification
- format_violation
- retry_failed
- syntax_or_runtime_error
- ambiguous_blocker_handled_poorly

## Variant Axes
Autoresearch should test Mighty Mouse variants across these axes:
- short vs medium vs detailed prompt length
- soft vs hard verification language
- generic vs explicit scope-control language
- compact vs sectioned response format
- minimal vs stronger retry instructions
- stronger honesty wording vs lighter wording

## Benchmark Design
Start with a focused benchmark pack tailored to Antigravity + Gemini 3 Flash.

### Bucket A: Simple Tasks
- one-file bug fixes
- small function completion
- simple validation fixes

### Bucket B: Medium Tasks
- two-file fixes
- constrained changes
- test-guided repairs
- preserve-existing-behavior edits

### Bucket C: Drift Traps
- misleading extra context
- nearby unrelated files
- explicit do-not-touch instructions
- temptation to over-edit

### Bucket D: Honesty Traps
- incomplete information
- unverifiable success claims
- missing tests
- ambiguous requirements

## Experiment Protocol
For each autoresearch iteration:
1. Select a Mighty Mouse variant.
2. Run the benchmark in Antigravity using the selected model.
3. Record all metrics and failure tags.
4. Compare against baseline and current best variant.
5. Promote only if scorecard improvement is measurable.
6. Extract lessons learned from failures before next iteration.

## Baseline Definition
Baseline = Gemini 3 Flash in Antigravity without Mighty Mouse.

All candidate variants should be compared against:
- baseline Gemini 3 Flash behavior
- current best Mighty Mouse variant

## Promotion Criteria
A variant should only be promoted when it:
- improves primary metrics materially
- does not introduce unacceptable verbosity or friction
- does not regress honesty or scope discipline
- remains usable as a normal slash-command workflow

## Stopping Criteria
Pause or stop a research run when:
- improvement plateaus across multiple consecutive iterations
- gains come only from verbosity inflation
- usability degrades despite metric gains
- host-environment instability invalidates signal

## Deliverables
Autoresearch should produce:
- best current Mighty Mouse variant
- scorecard results by variant
- failure analysis notes
- concise lessons learned
- recommended next prompt mutations

## Long-Term Packaging Goal
Once Mighty Mouse performs well in Antigravity with Gemini 3 Flash, package it as an installable slash-command or skill artifact that can later be adapted for other environments.

Antigravity + Gemini 3 Flash is the proving ground, not the final limit.
